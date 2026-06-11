import io
import os
import logging
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # headless server — must be set before pyplot is imported
from matplotlib import font_manager
import mplfinance as mpf
import yfinance as yf

from bot.services.stock import is_taiwan_stock

logger = logging.getLogger(__name__)

# 顯示期間（交易日）與抓取期間（多抓讓 MA60 完整）
PERIODS: dict[str, tuple[int, str, str]] = {
    "1m": (22, "6mo", "近 1 個月"),
    "3m": (66, "9mo", "近 3 個月"),
    "6m": (130, "1y", "近 6 個月"),
    "1y": (260, "2y", "近 1 年"),
}

_FONT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansTC-Regular.ttf")
)
_font_family: Optional[str] = None


def _ensure_font() -> Optional[str]:
    """Register NotoSansTC with matplotlib so Chinese titles render."""
    global _font_family
    if _font_family is not None:
        return _font_family
    if os.path.exists(_FONT_PATH):
        font_manager.fontManager.addfont(_FONT_PATH)
        _font_family = font_manager.FontProperties(fname=_FONT_PATH).get_name()
    else:
        _font_family = ""
    return _font_family


def render_chart(ticker: str, period_key: str, title_name: str = "") -> Optional[bytes]:
    """Render a daily candlestick PNG (volume + MA20/60). Returns None if no data."""
    days, fetch_period, _ = PERIODS[period_key]
    symbol = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker

    try:
        df = yf.Ticker(symbol).history(period=fetch_period, interval="1d", auto_adjust=False)
    except Exception as e:
        logger.warning("chart history failed for %s: %s", symbol, e)
        return None
    if df is None or df.empty or "Close" not in df.columns:
        return None

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()
    display = df.tail(days)
    if display.empty:
        return None

    addplots = []
    for col, color in (("MA20", "#f39c12"), ("MA60", "#8e44ad")):
        if display[col].notna().any():
            addplots.append(mpf.make_addplot(display[col], color=color, width=1.0))

    font = _ensure_font()
    rc = {"font.family": font} if font else {}
    # 台股習慣：紅漲綠跌
    mc = mpf.make_marketcolors(up="#e74c3c", down="#27ae60", edge="inherit",
                               wick="inherit", volume="in")
    style = mpf.make_mpf_style(base_mpf_style="yahoo", marketcolors=mc, rc=rc)

    title = f"{title_name}（{ticker}）" if title_name else ticker
    buf = io.BytesIO()
    mpf.plot(
        display,
        type="candle",
        volume=True,
        addplot=addplots,
        style=style,
        title=title,
        figsize=(10, 7),
        datetime_format="%y/%m/%d",
        tight_layout=True,
        savefig=dict(fname=buf, dpi=120),
    )
    return buf.getvalue()
