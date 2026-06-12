import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from bot.services.earnings import fetch_earnings_data
from bot.services.stock import is_taiwan_stock
from bot.services.watchlist import _load as _load_watchlists

logger = logging.getLogger(__name__)

_FILE = Path("data/earnings_watch.json")
_EXPIRE_DAYS = 2  # 預期日後 N 天仍未公布就放棄輪詢


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


def _all_watchlist_tickers() -> list[str]:
    tickers = []
    for raw in _load_watchlists().values():
        for t in (raw.keys() if isinstance(raw, dict) else raw):
            if t not in tickers:
                tickers.append(t)
    return tickers


def mark_pending(ticker: str, date_str: str) -> None:
    """登記今天要公布財報的股票，供輪詢 job 偵測公布。"""
    data = _load()
    existing = data.get(ticker)
    # 同一個財報日已分析過就不要重設（避免重複推送）
    if existing and existing.get("date") == date_str and existing.get("status") == "analyzed":
        return
    data[ticker] = {"date": date_str, "status": "pending", "updated": str(date.today())}
    _save(data)


def mark_analyzed(ticker: str) -> None:
    data = _load()
    if ticker in data:
        data[ticker]["status"] = "analyzed"
        data[ticker]["updated"] = str(date.today())
        _save(data)


def get_pending_announcements() -> dict[str, dict]:
    """回傳 {ticker: entry}：pending 且預期日 <= 今天（順便清掉過期項目）。"""
    data = _load()
    today = date.today()
    cutoff = str(today - timedelta(days=_EXPIRE_DAYS))
    kept = {t: e for t, e in data.items() if e.get("date", "") >= cutoff}
    if len(kept) != len(data):
        _save(kept)
    return {
        t: e for t, e in kept.items()
        if e.get("status") == "pending" and e.get("date", "") <= str(today)
    }


async def build_earnings_reminders() -> str:
    """掃自選股的下次財報日，回傳今天/明天的提醒文字（無則空字串）。

    當天公布者同時登記到輪詢清單，公布後會自動推送分析。
    台股在 yfinance 上常拿不到財報日，拿不到就跳過。
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    lines = []

    # 並行抓取；台股在 yfinance 上幾乎沒有財報日資料，直接跳過省時間
    tickers = [t for t in _all_watchlist_tickers() if not is_taiwan_stock(t)]
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
            mark_pending(ticker, next_date)
        elif next_date == str(tomorrow):
            lines.append(f"• {label} 明天（{tomorrow.strftime('%m/%d')}）公布財報")

    return "\n".join(lines)
