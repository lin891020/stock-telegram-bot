import asyncio
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import yfinance as yf

from bot.services.watchlist import get_watchlist_with_names, get_watchlist, add_ticker, remove_ticker, _load
from bot.services.news import fetch_and_summarize
from bot.services.stock import looks_like_ticker, search_ticker, get_stock_summary, is_taiwan_stock, clean_us_name
from bot.services.tw_stocks import get_tw_name, has_chinese, search_tw_stocks

logger = logging.getLogger(__name__)


def _label(ticker: str, name: str) -> str:
    if name and name != ticker:
        return f"{name}({ticker})"
    return ticker


def _build_watchlist_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{_label(i['ticker'], i['name'])}  ❌",
            callback_data=f"wdel_{i['ticker']}",
        )]
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
        await update.message.reply_text("請輸入股票代號或名稱，例如：/watch 2408 或 /watch 南亞科\n查看清單：/watchlist")
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
                    await update.message.reply_text(
                        f"找不到「{ticker}」，請確認代號是否正確\n"
                        f"或用名稱搜尋，例如：/watch Tesla"
                    )
                    return
                name = clean_us_name(raw_name) if raw_name else ticker
            except Exception:
                pass

        if add_ticker(user_id, ticker, name):
            label = _label(ticker, name)
            await update.message.reply_text(f"✅ 已加入追蹤：{label}\n\n每天早上 8 點會自動推送晨報")
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
            label = _label(r["symbol"], name)
            await update.message.reply_text(f"✅ 已加入追蹤：{label}\n\n每天早上 8 點會自動推送晨報")
        else:
            await update.message.reply_text(f"「{r['symbol']}」已在追蹤清單中")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"{_resolved_name(r)}({r['symbol']})",
            callback_data=f"wadd_{r['symbol']}_{_resolved_name(r)[:20]}",
        )]
        for r in results
    ]
    await update.message.reply_text("找到以下結果，請選擇：", reply_markup=InlineKeyboardMarkup(keyboard))


async def watch_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data[len("wadd_"):].split("_", 1)
    ticker = parts[0]
    raw_name = parts[1] if len(parts) > 1 else ticker
    name = raw_name if is_taiwan_stock(ticker) else clean_us_name(raw_name)

    user_id = query.from_user.id
    if add_ticker(user_id, ticker, name):
        label = _label(ticker, name)
        await query.edit_message_text(f"✅ 已加入追蹤：{label}\n\n每天早上 8 點會自動推送晨報")
    else:
        await query.edit_message_text(f"「{ticker}」已在追蹤清單中")


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
        await update.message.reply_text("請輸入要移除的代號或名稱，例如：/unwatch TSLA 或 /unwatch Tesla")
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
        await update.message.reply_text(summary, parse_mode="HTML")
    except Exception as e:
        logger.error("news_command failed: %s", e, exc_info=True)
        await update.message.reply_text("❌ 新聞抓取失敗，請稍後再試")


async def send_daily_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    all_data = _load()
    for user_id_str, raw in all_data.items():
        tickers = list(raw.keys()) if isinstance(raw, dict) else raw
        if not tickers:
            continue
        try:
            summary = await fetch_and_summarize(tickers)
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=f"📰 早安！追蹤股票晨報\n\n{summary}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Daily news failed for user %s: %s", user_id_str, e, exc_info=True)


async def send_closing_digest(context: ContextTypes.DEFAULT_TYPE, market: str) -> None:
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
                if isinstance(data, dict) and not data.get("error"):
                    lines.append(_format_closing_line(t, data))
            if lines:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=f"{title} {today}\n\n" + "\n".join(lines),
                )
        except Exception as e:
            logger.error("Closing digest failed for user %s: %s", user_id_str, e, exc_info=True)


async def send_tw_closing(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_closing_digest(context, "TW")


async def send_us_closing(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_closing_digest(context, "US")


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


def build_watch_handler(auth_filter):
    return [
        CommandHandler("watch", watch_command, filters=auth_filter),
        CommandHandler("unwatch", unwatch_command, filters=auth_filter),
        CommandHandler("watchlist", watchlist_command, filters=auth_filter),
        CommandHandler("news", news_command, filters=auth_filter),
        CommandHandler("testclosing", testclosing_command, filters=auth_filter),
        CallbackQueryHandler(watch_add_callback, pattern="^wadd_"),
        CallbackQueryHandler(watch_delete_callback, pattern="^wdel_"),
    ]
