import asyncio
import html
import logging
from datetime import date, datetime, time, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import yfinance as yf

from bot.auth import restrict_callback
from bot.handlers.messaging import send_long
from bot.handlers.pending import ask, register
from bot.services.watchlist import get_watchlist_with_names, get_watchlist, add_ticker, remove_ticker, _load
from bot.services.market import fetch_market_summary
from bot.services.news import fetch_and_summarize
from bot.services.settings import get_time, set_time, get_news_time, parse_hhmm
from bot.services.stock import looks_like_ticker, search_ticker, get_stock_summary, is_taiwan_stock, clean_us_name
from bot.services.tw_stocks import get_tw_name, has_chinese, search_tw_stocks

logger = logging.getLogger(__name__)

_NEWS_JOB_NAME = "daily_news"
_TAIPEI_UTC_OFFSET = 8  # Taipei has no DST


def _label(ticker: str, name: str) -> str:
    if name and name != ticker:
        return f"{name}({ticker})"
    return ticker


def _added_message(label: str) -> str:
    return f"✅ 已加入追蹤：{label}\n\n每天 {get_news_time()} 會自動推送晨報（/settime 可修改時間）"


def _wadd_callback_data(symbol: str, name: str) -> str:
    """Build wadd_ callback data within Telegram's 64-byte limit."""
    prefix = f"wadd_{symbol}_"
    budget = 64 - len(prefix.encode("utf-8"))
    truncated = name.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return prefix + truncated


def _build_watchlist_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    # 點名稱開股票卡片，點 ❌ 移除
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(_label(i["ticker"], i["name"]), callback_data=f"card_{i['ticker']}"),
            InlineKeyboardButton("❌", callback_data=f"wdel_{i['ticker']}"),
        ]
        for i in items
    ])


def _format_closing_line(ticker: str, data: dict) -> str:
    price = data.get("price") or data.get("close")
    prev = data.get("prev_close")
    name = data.get("name", "")
    label = _label(ticker, name)
    currency = "元" if data.get("market") == "TW" else "USD"

    if not price:
        return f"{label}  無資料"

    if prev and prev != 0:
        change = price - prev
        pct = change / prev * 100
        arrow = "▲" if change >= 0 else "▼"
        sign = "+" if change >= 0 else ""
        return f"{label}  收 {price:.2f} {currency}  {arrow} {sign}{pct:.2f}%（{sign}{change:.2f}）"

    return f"{label}  收 {price:.2f} {currency}"


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await ask(update.message, context, "watch", "輸入要加入追蹤的代號或名稱：")
        return

    query_text = " ".join(context.args).strip()

    if looks_like_ticker(query_text):
        ticker = query_text.upper()
        name = ticker

        if is_taiwan_stock(ticker):
            tw_name = get_tw_name(ticker)
            if tw_name is None:
                # Validate by fetching — cache might not cover all stocks
                test = await get_stock_summary(ticker)
                if test.get("error"):
                    await update.message.reply_text(
                        f"找不到台股代號「{ticker}」，請確認是否正確"
                    )
                    return
            name = tw_name or ticker
        else:
            try:
                info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                raw_name = info.get("shortName") or info.get("longName")
                if not price and not raw_name:
                    # Ticker not found — fall through to name search
                    results = await asyncio.to_thread(search_ticker, query_text)
                    results = results[:5]
                    if not results:
                        await update.message.reply_text(
                            f"找不到「{query_text}」，請確認股票代號或名稱是否正確"
                        )
                        return
                    if len(results) == 1:
                        r = results[0]
                        clean = clean_us_name(r["name"])
                        if add_ticker(user_id, r["symbol"], clean):
                            await update.message.reply_text(_added_message(_label(r["symbol"], clean)))
                        else:
                            await update.message.reply_text(f"「{r['symbol']}」已在追蹤清單中")
                        return
                    keyboard = [
                        [InlineKeyboardButton(
                            f"{clean_us_name(r['name'])}({r['symbol']})",
                            callback_data=_wadd_callback_data(r["symbol"], clean_us_name(r["name"])),
                        )]
                        for r in results
                    ]
                    await update.message.reply_text("找到以下結果，請選擇：", reply_markup=InlineKeyboardMarkup(keyboard))
                    return
                name = clean_us_name(raw_name) if raw_name else ticker
            except Exception:
                pass

        if add_ticker(user_id, ticker, name):
            await update.message.reply_text(_added_message(_label(ticker, name)))
        else:
            await update.message.reply_text(f"「{_label(ticker, name)}」已在追蹤清單中")
        return

    await update.message.reply_text(f"搜尋「{query_text}」中...")

    # Chinese query → search TW stock cache; otherwise use yfinance
    if has_chinese(query_text):
        results = search_tw_stocks(query_text, max_results=5)
    else:
        results = await asyncio.to_thread(search_ticker, query_text)
        results = results[:5]

    if not results:
        await update.message.reply_text(f"找不到「{query_text}」，請直接輸入股票代號，例如：/watch 2408")
        return

    def _resolved_name(r: dict) -> str:
        name = r["name"]
        return name if is_taiwan_stock(r["symbol"]) else clean_us_name(name)

    if len(results) == 1:
        r = results[0]
        name = _resolved_name(r)
        if add_ticker(user_id, r["symbol"], name):
            await update.message.reply_text(_added_message(_label(r["symbol"], name)))
        else:
            await update.message.reply_text(f"「{r['symbol']}」已在追蹤清單中")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"{_resolved_name(r)}({r['symbol']})",
            callback_data=_wadd_callback_data(r["symbol"], _resolved_name(r)),
        )]
        for r in results
    ]
    await update.message.reply_text("找到以下結果，請選擇：", reply_markup=InlineKeyboardMarkup(keyboard))


@restrict_callback
async def watch_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data[len("wadd_"):].split("_", 1)
    ticker = parts[0]
    raw_name = parts[1] if len(parts) > 1 else ticker
    name = raw_name if is_taiwan_stock(ticker) else clean_us_name(raw_name)

    user_id = query.from_user.id
    if add_ticker(user_id, ticker, name):
        await query.edit_message_text(_added_message(_label(ticker, name)))
    else:
        await query.edit_message_text(f"「{ticker}」已在追蹤清單中")


@restrict_callback
async def watch_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ticker = query.data[len("wdel_"):]
    user_id = query.from_user.id
    remove_ticker(user_id, ticker)

    items = get_watchlist_with_names(user_id)
    if not items:
        await query.edit_message_text("📋 追蹤清單已清空\n\n新增：/watch 2330 或 /watch 台積電")
        return

    await query.edit_message_reply_markup(reply_markup=_build_watchlist_keyboard(items))


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await ask(update.message, context, "unwatch", "輸入要移除追蹤的代號或名稱：")
        return

    query_text = " ".join(context.args).strip()
    ticker = query_text.upper()

    # Try exact ticker match first
    if not remove_ticker(user_id, ticker):
        # Fall back to name match
        items = get_watchlist_with_names(user_id)
        match = next(
            (i for i in items if i["name"].upper() == query_text.upper()),
            None
        )
        if match:
            remove_ticker(user_id, match["ticker"])
            label = _label(match["ticker"], match["name"])
            await update.message.reply_text(f"✅ 已移除追蹤：{label}")
        else:
            await update.message.reply_text(f"「{query_text}」不在追蹤清單中")
        return

    await update.message.reply_text(f"✅ 已移除追蹤：{ticker}")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    items = get_watchlist_with_names(user_id)

    if not items:
        await update.message.reply_text("追蹤清單是空的。\n\n新增：/watch 2330 或 /watch 台積電\n移除：/unwatch 2330")
        return

    await update.message.reply_text(
        "📋 追蹤清單（點 ❌ 移除）：",
        reply_markup=_build_watchlist_keyboard(items),
    )


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    tickers = get_watchlist(user_id)

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
    taipei_now = datetime.now(timezone.utc) + timedelta(hours=_TAIPEI_UTC_OFFSET)
    if taipei_now.weekday() >= 5:  # 5=Sat, 6=Sun
        return
    all_data = _load()
    today = date.today().strftime("%m/%d")
    for user_id_str, raw in all_data.items():
        tickers = list(raw.keys()) if isinstance(raw, dict) else raw
        if not tickers:
            continue
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


async def send_closing_digest(context: ContextTypes.DEFAULT_TYPE, market: str) -> None:
    if datetime.now(timezone.utc).weekday() >= 5:  # 5=Sat, 6=Sun — markets closed
        return
    today = date.today().strftime("%Y/%m/%d")
    title = "📊 台股收盤速報" if market == "TW" else "📊 美股收盤速報"
    all_data = _load()

    for user_id_str, raw in all_data.items():
        tickers = list(raw.keys()) if isinstance(raw, dict) else raw
        filtered = [t for t in tickers if is_taiwan_stock(t) == (market == "TW")]
        if not filtered:
            continue
        try:
            results = await asyncio.gather(*[get_stock_summary(t) for t in filtered])
            lines = []
            for t, data in zip(filtered, results):
                if not isinstance(data, dict) or data.get("error"):
                    continue
                # For TW stocks, skip if data date doesn't match today (holiday)
                if market == "TW":
                    data_date = (data.get("date") or "")[:10]
                    today_iso = date.today().strftime("%Y/%m/%d")
                    if data_date and data_date.replace("-", "/") != today_iso:
                        continue
                lines.append(_format_closing_line(t, data))
            if lines:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=f"{title} {today}\n\n" + "\n".join(lines),
                )
        except Exception as e:
            logger.error("Closing digest failed for user %s: %s", user_id_str, e, exc_info=True)


def _schedule_named_daily(job_queue, name: str, time_key: str, callback) -> None:
    """(Re)schedule a named daily job from the saved Taipei-time setting."""
    for job in job_queue.get_jobs_by_name(name):
        job.schedule_removal()
    hour, minute = parse_hhmm(get_time(time_key))
    job_queue.run_daily(
        callback,
        time=time(hour=(hour - _TAIPEI_UTC_OFFSET) % 24, minute=minute, tzinfo=timezone.utc),
        name=name,
    )
    logger.info("Job %s scheduled at %s Taipei", name, get_time(time_key))


def schedule_daily_news(job_queue) -> None:
    _schedule_named_daily(job_queue, _NEWS_JOB_NAME, "news", send_daily_news)


def schedule_tw_closing(job_queue) -> None:
    _schedule_named_daily(job_queue, "tw_closing", "tw_close", send_tw_closing)


_SETTIME_TARGETS = {
    "news": ("起床報", "news", schedule_daily_news),
    "tw": ("台股收盤速報", "tw_close", schedule_tw_closing),
}


def _settime_keyboard() -> InlineKeyboardMarkup:
    news_row = [
        InlineKeyboardButton(t, callback_data=f"stime_news_{t}")
        for t in ("05:30", "06:00", "06:30", "07:00", "07:30")
    ]
    tw_row = [
        InlineKeyboardButton(t, callback_data=f"stime_tw_{t}")
        for t in ("14:00", "14:30", "15:00")
    ]
    return InlineKeyboardMarkup([news_row, tw_row])


async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set push times. Usage: /settime 06:30 (起床報) | /settime tw 14:30"""
    if not context.args:
        await update.message.reply_text(
            "目前推送時間（台北時間，週末不推送）：\n"
            f"• 起床報（含隔夜美股收盤）：{get_time('news')}\n"
            f"• 台股收盤速報：{get_time('tw_close')}\n\n"
            "點按鈕直接改（上排：起床報，下排：台股收盤），\n"
            "或輸入自訂時間：/settime 06:45、/settime tw 14:10",
            reply_markup=_settime_keyboard(),
        )
        return

    if len(context.args) >= 2 and context.args[0].lower() in _SETTIME_TARGETS:
        target_key = context.args[0].lower()
        raw = context.args[1]
    else:
        target_key = "news"
        raw = context.args[0]

    label, time_key, reschedule = _SETTIME_TARGETS[target_key]

    if parse_hhmm(raw) is None:
        await update.message.reply_text(
            "時間格式錯誤，請用 24 小時制 HH:MM，例如：\n/settime 08:30\n/settime tw 14:30"
        )
        return

    normalized = set_time(time_key, raw)
    reschedule(context.job_queue)
    await update.message.reply_text(f"✅ {label}時間已改為每天 {normalized}（台北時間，週末不推送）")


@restrict_callback
async def settime_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settime 預設時間按鈕：stime_{key}_{HH:MM}"""
    query = update.callback_query
    await query.answer()

    _, target_key, raw = query.data.split("_", 2)
    if target_key not in _SETTIME_TARGETS or parse_hhmm(raw) is None:
        await query.edit_message_text("❌ 無效的時間選項，請重新使用 /settime")
        return

    label, time_key, reschedule = _SETTIME_TARGETS[target_key]
    normalized = set_time(time_key, raw)
    reschedule(context.job_queue)
    await query.edit_message_text(f"✅ {label}時間已改為每天 {normalized}（台北時間，週末不推送）")


async def send_tw_closing(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_closing_digest(context, "TW")


async def testclosing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger closing digest for testing. Usage: /testclosing tw | us"""
    market = (context.args[0].upper() if context.args else "TW")
    if market not in ("TW", "US"):
        await update.message.reply_text("用法：/testclosing tw 或 /testclosing us")
        return

    user_id = update.effective_user.id
    tickers = get_watchlist(user_id)
    filtered = [t for t in tickers if is_taiwan_stock(t) == (market == "TW")]

    if not filtered:
        await update.message.reply_text(f"自選股裡沒有{'台股' if market == 'TW' else '美股'}")
        return

    today = date.today().strftime("%Y/%m/%d")
    title = "📊 台股收盤速報" if market == "TW" else "📊 美股收盤速報"
    results = await asyncio.gather(*[get_stock_summary(t) for t in filtered])
    lines = []
    for t, data in zip(filtered, results):
        if isinstance(data, dict) and not data.get("error"):
            lines.append(_format_closing_line(t, data))

    if lines:
        await update.message.reply_text(f"{title} {today}\n\n" + "\n".join(lines))
    else:
        await update.message.reply_text("無法取得報價資料")


@register("watch")
async def _pending_watch(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await watch_command(update, context)


@register("unwatch")
async def _pending_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await unwatch_command(update, context)


def build_watch_handler(auth_filter):
    return [
        CommandHandler("watch", watch_command, filters=auth_filter),
        CommandHandler("unwatch", unwatch_command, filters=auth_filter),
        CommandHandler("watchlist", watchlist_command, filters=auth_filter),
        CommandHandler("news", news_command, filters=auth_filter),
        CommandHandler("settime", settime_command, filters=auth_filter),
        CommandHandler("testclosing", testclosing_command, filters=auth_filter),
        CallbackQueryHandler(watch_add_callback, pattern="^wadd_"),
        CallbackQueryHandler(watch_delete_callback, pattern="^wdel_"),
        CallbackQueryHandler(settime_pick_callback, pattern="^stime_"),
    ]
