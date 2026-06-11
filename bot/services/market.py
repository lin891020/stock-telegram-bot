import asyncio
import logging

import yfinance as yf

logger = logging.getLogger(__name__)

# (顯示名稱, yfinance symbol, 小數位數)
_INDICES = [
    ("加權指數", "^TWII", 0),
    ("S&P 500", "^GSPC", 0),
    ("NASDAQ", "^IXIC", 0),
    ("道瓊", "^DJI", 0),
    ("費城半導體", "^SOX", 0),
    ("美元/台幣", "TWD=X", 3),
]


def _fetch_quote(symbol: str) -> tuple:
    """Return (last_price, prev_close) or (None, None) on failure."""
    try:
        info = yf.Ticker(symbol).fast_info
        return info.last_price, info.previous_close
    except Exception as e:
        logger.warning("market quote failed for %s: %s", symbol, e)
        return None, None


def _format_line(name: str, price, prev, digits: int) -> str:
    if price is None:
        return f"{name}  無資料"
    if prev:
        change = price - prev
        pct = change / prev * 100
        arrow = "▲" if change >= 0 else "▼"
        sign = "+" if change >= 0 else ""
        return f"{name}  {price:,.{digits}f}  {arrow} {sign}{pct:.2f}%"
    return f"{name}  {price:,.{digits}f}"


def _fetch_market_summary_sync() -> str:
    lines = [
        _format_line(name, *_fetch_quote(symbol), digits)
        for name, symbol, digits in _INDICES
    ]
    return "\n".join(lines)


async def fetch_market_summary() -> str:
    """大盤速覽文字區塊（加權 + 美股三大 + 費半 + 台幣）。"""
    return await asyncio.to_thread(_fetch_market_summary_sync)
