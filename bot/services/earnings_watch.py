"""財報公布偵測：盯所有自選股，出現新一季實際 EPS 就推播。

不需要事前登記。狀態檔只記每支「已知最新一季財報日」當基準，
第一次看到某支股票時只寫基準、不推播，避免上線當下把舊財報全推一遍。
"""
import asyncio
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from bot.services.store import load_json, save_json

from bot.services.earnings import fetch_earnings_data
from bot.services.filings import EARNINGS_FORMS, fetch_earnings_release, get_cik, list_filings
from bot.services.stock import is_taiwan_stock
from bot.services.watchlist import all_tickers

logger = logging.getLogger(__name__)

_FILE = Path("data/earnings_watch.json")


def _load() -> dict:
    return load_json(_FILE, {})


def _save(data: dict) -> None:
    save_json(_FILE, data)


def all_watchlist_tickers() -> list[str]:
    return all_tickers()


def latest_reported_date(data: dict) -> Optional[str]:
    """最新一季「已公布實際 EPS」的財報日（ISO 字串），沒有回 None。"""
    dates = [
        q["date"] for q in data.get("quarters", [])
        if q.get("eps_actual") is not None and q.get("date")
    ]
    return max(dates) if dates else None


# 兩條訊號各自的「已推播到哪一季」基準。commit_event 會同時推進兩個——
# 只推進觸發的那一條，另一條下一輪就會對同一季再推一次。
_EVENT_FIELDS = ("last_filing", "last_reported")


def _peek(field: str, ticker: str) -> Optional[str]:
    return (_load().get(ticker) or {}).get(field)


def _set(field: str, ticker: str, value: str) -> None:
    state = _load()
    entry = state.get(ticker) or {}
    entry[field] = value
    entry["updated"] = str(date.today())
    state[ticker] = entry
    _save(state)


def _is_new(field: str, ticker: str, latest: Optional[str]) -> bool:
    """latest 是否比基準新。沒有基準時只建基準並回 False（不推播）。

    第一次看到某支股票就推播的話，上線當下會把所有舊財報全推一遍。
    """
    if not latest:
        return False
    known = _peek(field, ticker)
    if known is None:
        _set(field, ticker, latest)
        return False
    return latest > known


def detect_new_report(ticker: str, data: dict) -> Optional[str]:
    """比對基準，回傳新公布的財報日；首次建立基準時回 None（不推播）。

    ⚠️ 只偵測，不推進基準——推進要等推播真的成功，由 commit_event 做。
    以前是偵測時就寫死基準，只要接下來的 build_brief 出錯（LLM 逾時、
    SEC 限流），那一季的財報就永遠不會再被推播了。
    """
    latest = latest_reported_date(data)
    return latest if _is_new("last_reported", ticker, latest) else None


def commit_event(ticker: str, event_date: str) -> None:
    """推播成功後才推進基準；兩條訊號一起推進。

    SEC 申報與 yfinance 的 EPS 更新講的是同一季，但基準各記各的。
    只推進觸發的那一條，另一條會在下一輪對同一季再推一次
    ——實測 SEC 先推一次、一小時後 EPS 又推一次。
    """
    for field in _EVENT_FIELDS:
        known = _peek(field, ticker)
        if known is None or event_date > known:
            _set(field, ticker, event_date)


def _newest_filing_date(ticker: str) -> Optional[str]:
    """只問「最近一次 8-K/6-K 是哪天」——一個請求就夠。"""
    cik = get_cik(ticker)
    if cik is None:
        return None
    filings = list_filings(cik, EARNINGS_FORMS, limit=1)
    return filings[0]["date"] if filings else None


async def detect_new_filing(ticker: str) -> Optional[str]:
    """官方申報流偵測：SEC 出現新的財報新聞稿就回傳申報日。

    這是主要訊號。EDGAR 是第一手、公司送件當下就有，而且觸發的同時
    就把報告要用的原文一起拿到了。台股沒有 SEC 申報，回 None 交給 EPS 訊號。

    完整掃描要走 10-20 個 SEC 請求（逐份查 Item 2.02、列附件、抓內文），
    每小時對每支美股都跑一次太浪費。先用一個請求問「最新申報日」當閘門，
    沒有新東西就直接返回；穩態下每支股票每輪只花一個請求。
    """
    if is_taiwan_stock(ticker):
        return None

    newest = await asyncio.to_thread(_newest_filing_date, ticker)
    if not newest:
        return None
    # 大部分 8-K 不是財報（人事、協議、交車數量），所以 last_seen 與
    # last_filing 要分開記：前者是閘門，後者才是真正的財報基準。
    if newest == _peek("last_seen_filing", ticker):
        return None
    # 閘門立即推進：它只表示「這份申報我已經檢查過了」，與推播成功無關。
    # 大部分 8-K 不是財報，不推進的話每輪都要重掃 10-20 個 SEC 請求。
    _set("last_seen_filing", ticker, newest)

    release = await asyncio.to_thread(fetch_earnings_release, ticker)
    if not release:
        return None
    return release["filed"] if _is_new("last_filing", ticker, release["filed"]) else None


async def detect_earnings_event(ticker: str) -> Optional[dict]:
    """回傳 {"date":..., "signal": "SEC 申報"|"EPS 更新"} 或 None。

    官方申報為主、yfinance 的 EPS 為輔：EDGAR 給不了 beat/miss（它只有
    公司實際數字，沒有分析師預期），所以兩條訊號都要留著。
    """
    filed = await detect_new_filing(ticker)
    if filed:
        return {"date": filed, "signal": "SEC 申報"}

    data = await fetch_earnings_data(ticker)
    if data.get("error"):
        return None
    reported = detect_new_report(ticker, data)
    if reported:
        return {"date": reported, "signal": "EPS 更新"}
    return None


def prune_state(tickers: list[str]) -> None:
    """移除已不在自選股的紀錄，避免狀態檔無限長大。"""
    state = _load()
    kept = {t: e for t, e in state.items() if t in tickers}
    if len(kept) != len(state):
        _save(kept)


async def build_earnings_reminders() -> str:
    """掃自選股的下次財報日，回傳今天/明天的提醒文字（無則空字串）。

    台股在 yfinance 上幾乎拿不到「下次財報日」，掃了也是空的，直接跳過省時間。
    （實際公布的偵測不受影響：poll 會掃所有自選股，含台股。）
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    lines = []

    tickers = [t for t in all_watchlist_tickers() if not is_taiwan_stock(t)]
    if not tickers:
        return ""
    results = await asyncio.gather(
        *[fetch_earnings_data(t) for t in tickers], return_exceptions=True
    )

    for ticker, data in zip(tickers, results):
        if isinstance(data, Exception):
            logger.warning("earnings reminder fetch failed for %s: %s", ticker, data)
            continue
        if data.get("error"):
            continue
        next_date = data.get("next_earnings_date")
        if not next_date:
            continue

        name = data.get("name", "")
        label = f"{name}({ticker})" if name and name != ticker else ticker
        if next_date == str(today):
            lines.append(f"• {label} 今天公布財報（公布後會自動推送分析）")
        elif next_date == str(tomorrow):
            lines.append(f"• {label} 明天（{tomorrow.strftime('%m/%d')}）公布財報")

    return "\n".join(lines)
