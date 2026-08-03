"""財報公布偵測：盯所有自選股，出現新一季實際 EPS 就推播。

不需要事前登記。狀態檔只記每支「已知最新一季財報日」當基準，
第一次看到某支股票時只寫基準、不推播，避免上線當下把舊財報全推一遍。
"""
import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from bot.services.earnings import fetch_earnings_data
from bot.services.stock import is_taiwan_stock
from bot.services.watchlist import _load as _load_watchlists

logger = logging.getLogger(__name__)

_FILE = Path("data/earnings_watch.json")


def _load() -> dict:
    if not _FILE.exists():
        return {}
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _FILE.parent.mkdir(exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def all_watchlist_tickers() -> list[str]:
    tickers = []
    for raw in _load_watchlists().values():
        for t in (raw.keys() if isinstance(raw, dict) else raw):
            if t not in tickers:
                tickers.append(t)
    return tickers


def latest_reported_date(data: dict) -> Optional[str]:
    """最新一季「已公布實際 EPS」的財報日（ISO 字串），沒有回 None。"""
    dates = [
        q["date"] for q in data.get("quarters", [])
        if q.get("eps_actual") is not None and q.get("date")
    ]
    return max(dates) if dates else None


def detect_new_report(ticker: str, data: dict) -> Optional[str]:
    """比對基準，回傳新公布的財報日；首次建立基準時回 None（不推播）。"""
    latest = latest_reported_date(data)
    if not latest:
        return None

    state = _load()
    known = (state.get(ticker) or {}).get("last_reported")
    if known == latest:
        return None

    state[ticker] = {"last_reported": latest, "updated": str(date.today())}
    _save(state)

    # 沒有基準（第一次見到）或資料往回跳，都不推播
    if known is None or latest <= known:
        return None
    return latest


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
