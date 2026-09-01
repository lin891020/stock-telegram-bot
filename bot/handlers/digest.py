"""定時推播的**內容**：起床報與收盤速報。

跟 schedule.py 的分工：這裡決定「推什麼」，那裡決定「幾點推」。
以前兩者跟自選股增刪查擠在同一個 500 行的 watch.py 裡，想改晨報的
版面得先在三種職責之間找路。

推播對象一律走 iter_watchlists()，不假設只有一個使用者。
"""
import asyncio
import html
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.handlers.messaging import send_long
from bot.services import clock
from bot.services.formatting import name_label, price_with_change, quote_line
from bot.services.market import fetch_market_summary
from bot.services.news import fetch_and_summarize
from bot.services.stock import get_stock_summary, intraday_quote, is_taiwan_stock
from bot.services.watchlist import get_watchlist, iter_watchlists

logger = logging.getLogger(__name__)


# ── 收盤速報 ──────────────────────────────────────────────────────────

def _closing_title(market: str) -> str:
    return "📊 台股收盤速報" if market == "TW" else "📊 美股收盤速報"


def _is_stale_tw_quote(data: dict) -> bool:
    """台股遇到休市日會回前一個交易日的收盤價，那不該當成「今天的收盤」。"""
    data_date = (data.get("date") or "")[:10].replace("-", "/")
    return bool(data_date) and data_date != clock.today_str("%Y/%m/%d")


async def _closing_lines(tickers: list[str], market: str, skip_stale: bool) -> list[str]:
    """組出收盤速報的每一行。

    定時推播要濾掉休市日的舊報價（否則週一到週五每天推同一個數字），
    但 /testclosing 是手動觸發、目的就是看現在抓到什麼，不該濾。
    """
    results = await asyncio.gather(*[get_stock_summary(t) for t in tickers])
    lines = []
    for ticker, data in zip(tickers, results):
        if not isinstance(data, dict) or data.get("error"):
            continue
        if skip_stale and market == "TW" and _is_stale_tw_quote(data):
            continue
        # 標題已經寫了日期；skip_stale 保證每一行都是今天的，所以不重複掛
        lines.append(quote_line(ticker, data, show_date=not skip_stale))
    return lines


def _for_market(tickers, market: str) -> list[str]:
    return [t for t in tickers if is_taiwan_stock(t) == (market == "TW")]


async def send_closing_digest(context: ContextTypes.DEFAULT_TYPE, market: str) -> None:
    if clock.is_weekend():
        return
    today = clock.today_str("%Y/%m/%d")

    for user_id_str, items in iter_watchlists():
        tickers = _for_market(items, market)
        if not tickers:
            continue
        try:
            lines = await _closing_lines(tickers, market, skip_stale=True)
            if lines:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=f"{_closing_title(market)} {today}\n\n" + "\n".join(lines),
                )
        except Exception as e:
            logger.error("Closing digest failed for user %s: %s", user_id_str, e, exc_info=True)


async def send_tw_closing(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_closing_digest(context, "TW")


async def send_us_closing(context: ContextTypes.DEFAULT_TYPE) -> None:
    """美股收盤速報。

    美股 16:00 ET 收盤，換算台北是隔天清晨 04:00（夏令）或 05:00（冬令），
    所以預設排在 05:30——兩種都涵蓋，而且還在 06:30 起床報之前。
    """
    await send_closing_digest(context, "US")


# ── 盤中速報 ──────────────────────────────────────────────────────────

async def _intraday_lines(tickers: list[str]) -> list[str]:
    """盤中的每一行。

    ⚠️ 這裡不能用 get_stock_summary：台股報價走 TWSE 盤後結算，中午查
    只會拿到**前一個交易日**的收盤價，而畫面上看不出來。走 yfinance 的
    即時價（跟價格提醒同一條路），並標「現價」而不是「收」。
    """
    quotes = await asyncio.gather(*[intraday_quote(t) for t in tickers])
    lines = []
    for ticker, (price, prev) in zip(tickers, quotes):
        if price is None:
            continue
        market = "TW" if is_taiwan_stock(ticker) else "US"
        label = name_label(ticker, _watch_name(ticker))
        lines.append(f"{label}  現價 {price_with_change(price, prev, market)}")
    return lines


def _watch_name(ticker: str) -> str:
    for _, items in iter_watchlists():
        if ticker in items:
            return items[ticker] or ""
    return ""


async def send_noon_snapshot(context: ContextTypes.DEFAULT_TYPE) -> None:
    """台股盤中速報（預設中午 12:00，台股 09:00–13:30 開盤中）。"""
    if clock.is_weekend():
        return
    for user_id_str, items in iter_watchlists():
        tickers = _for_market(items, "TW")
        if not tickers:
            continue
        try:
            lines = await _intraday_lines(tickers)
            if lines:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=f"🕛 台股盤中速報 {clock.today_str('%m/%d')} "
                         f"{clock.now():%H:%M}\n\n" + "\n".join(lines),
                )
        except Exception as e:
            logger.error("Noon snapshot failed for user %s: %s", user_id_str, e, exc_info=True)


# ── 起床報 ────────────────────────────────────────────────────────────

async def _build_morning_header(user_id: int = 0) -> str:
    """大盤＋今日大事（財報日、掛著的提醒），任一失敗都不影響晨報主體。"""
    parts = []
    try:
        market = await fetch_market_summary()
        if market:
            parts.append(f"🌐 大盤（隔夜美股已收）\n{html.escape(market)}")
    except Exception as e:
        logger.warning("morning market summary failed: %s", e)

    today_lines = []
    try:
        from bot.services.earnings_watch import build_earnings_reminders
        reminders = await build_earnings_reminders()
        if reminders:
            today_lines.append(reminders)
    except Exception as e:
        logger.warning("morning earnings reminders failed: %s", e)

    try:
        from bot.services.alerts import get_alerts
        count = len(get_alerts(user_id)) if user_id else 0
        if count:
            today_lines.append(f"• 🔔 掛著 {count} 個價格提醒（/alert 查看）")
    except Exception as e:
        logger.warning("morning alerts count failed: %s", e)

    if today_lines:
        parts.append("📋 今天\n" + "\n".join(today_lines))

    return "\n\n".join(parts)


async def send_daily_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    if clock.is_weekend():
        return
    today = clock.today_str("%m/%d")

    for user_id_str, items in iter_watchlists():
        tickers = list(items)
        try:
            header = await _build_morning_header(int(user_id_str))
            summary = await fetch_and_summarize(tickers)
            header_block = f"{header}\n\n" if header else ""
            await send_long(
                context.bot,
                int(user_id_str),
                f"📰 早安！{today} 起床報\n\n{header_block}{summary}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Daily news failed for user %s: %s", user_id_str, e, exc_info=True)
            # 主動告知，否則使用者只會「咦今天沒收到晨報」而不知道掛了
            try:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=(f"⚠️ 今天 {today} 起床報抓取失敗（資料源可能暫時異常），"
                          "可稍後用 /news 重試或 /health 檢查。"),
                )
            except Exception:
                pass


# ── 手動觸發 ──────────────────────────────────────────────────────────

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/news — 起床報的新聞區塊，隨時想看就看。"""
    tickers = get_watchlist(update.effective_user.id)
    if not tickers:
        await update.message.reply_text("追蹤清單是空的，請先用 /watch <代號> 加入股票")
        return

    await update.message.reply_text(f"⏳ 正在整理 {', '.join(tickers)} 的最新新聞...")
    try:
        summary = await fetch_and_summarize(tickers)
        await send_long(context.bot, update.effective_chat.id, summary, parse_mode="HTML")
    except Exception as e:
        logger.error("news_command failed: %s", e, exc_info=True)
        await update.message.reply_text("❌ 新聞抓取失敗，請稍後再試")


async def testclosing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/testclosing tw|us — 不等排程，現在就看收盤速報長什麼樣。"""
    market = (context.args[0].upper() if context.args else "TW")
    if market not in ("TW", "US"):
        await update.message.reply_text("用法：/testclosing tw 或 /testclosing us")
        return

    tickers = _for_market(get_watchlist(update.effective_user.id), market)
    if not tickers:
        await update.message.reply_text(f"自選股裡沒有{'台股' if market == 'TW' else '美股'}")
        return

    # 手動觸發不濾休市日的舊報價——目的就是看現在抓到什麼
    lines = await _closing_lines(tickers, market, skip_stale=False)
    if not lines:
        await update.message.reply_text("無法取得報價資料")
        return
    await update.message.reply_text(
        f"{_closing_title(market)} {clock.today_str('%Y/%m/%d')}\n\n" + "\n".join(lines)
    )


def build_digest_handler(auth_filter):
    return [
        CommandHandler("news", news_command, filters=auth_filter),
        CommandHandler("testclosing", testclosing_command, filters=auth_filter),
    ]
