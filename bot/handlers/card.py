"""股票卡片：直接傳代號或名稱（不用指令）就回報價卡片＋操作按鈕。

按鈕直接重用既有 callback：apick_（分析類型選單）、epick_（財報分析）、
wadd_（加自選）、chartp_（K 線，chart.py）。
"""
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters

from bot.auth import restrict_callback
from bot.handlers.alert import ask_alert_condition
from bot.handlers.analyze import _analysis_keyboard
from bot.handlers.earnings import _run_earnings_analysis
from bot.handlers.messaging import reply_long
from bot.handlers.pending import dispatch_pending
from bot.services.formatting import quote_line
from bot.services.recent import add_recent
from bot.services.watchlist import add_ticker
from bot.services.stock import (
    get_stock_summary, looks_like_ticker, search_ticker, is_taiwan_stock, clean_us_name,
)
from bot.services.tw_stocks import has_chinese, search_tw_stocks

logger = logging.getLogger(__name__)

_MAX_QUERY_LEN = 20  # 超過就當聊天雜訊，不回應


def _card_keyboard(ticker: str, name: str) -> InlineKeyboardMarkup:
    # 卡片專用 callback（cana_/cearn_/cadd_）：操作一律 reply 新訊息，卡片留在原地
    cadd_prefix = f"cadd_{ticker}_"
    budget = 64 - len(cadd_prefix.encode("utf-8"))
    safe_name = (name or ticker).encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 深度分析", callback_data=f"cana_{ticker}"),
            InlineKeyboardButton("📈 K線", callback_data=f"chartp_{ticker}_6m"),
        ],
        [
            InlineKeyboardButton("📋 財報", callback_data=f"cearn_{ticker}"),
            InlineKeyboardButton("🔔 設提醒", callback_data=f"ahint_{ticker}"),
        ],
        [InlineKeyboardButton("👀 加自選", callback_data=cadd_prefix + safe_name)],
    ])


def _card_text(ticker: str, data: dict) -> str:
    return quote_line(ticker, data, multiline=True)


async def send_stock_card(message, ticker: str) -> None:
    ticker = ticker.upper().strip()
    data = await get_stock_summary(ticker)
    if not isinstance(data, dict) or data.get("error"):
        await message.reply_text(f"查無「{ticker}」的報價，請確認代號是否正確")
        return
    name = data.get("name", "")
    add_recent(ticker, name)
    await message.reply_text(
        _card_text(ticker, data),
        reply_markup=_card_keyboard(ticker, name),
    )


async def text_lookup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """純文字（非指令）：先看有沒有等待中的兩段式輸入，否則代號出卡片、名稱搜尋。"""
    if await dispatch_pending(update, context):
        return

    query = (update.message.text or "").strip()
    if not query or len(query) > _MAX_QUERY_LEN:
        return

    if looks_like_ticker(query):
        await send_stock_card(update.message, query)
        return

    if has_chinese(query):
        results = search_tw_stocks(query)
    else:
        results = await asyncio.to_thread(search_ticker, query)

    if not results:
        await update.message.reply_text(
            f"找不到「{query}」相關的股票。\n直接傳代號試試，例如：2330、NVDA"
        )
        return

    if len(results) == 1:
        await send_stock_card(update.message, results[0]["symbol"])
        return

    def _display(r: dict) -> str:
        return r["name"] if is_taiwan_stock(r["symbol"]) else clean_us_name(r["name"])

    keyboard = [
        [InlineKeyboardButton(
            f"{_display(r)}({r['symbol']})",
            callback_data=f"card_{r['symbol']}",
        )]
        for r in results
    ]
    await update.message.reply_text(
        "找到以下結果，請選擇：", reply_markup=InlineKeyboardMarkup(keyboard)
    )


@restrict_callback
async def card_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    ticker = query.data[len("card_"):]
    await send_stock_card(query.message, ticker)


@restrict_callback
async def card_analyze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """卡片的 📊：另發分析類型選單，卡片留著。"""
    query = update.callback_query
    await query.answer()
    ticker = query.data[len("cana_"):]
    await query.message.reply_text(
        f"選擇 {ticker} 的分析類型：", reply_markup=_analysis_keyboard(ticker)
    )


@restrict_callback
async def card_earnings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """卡片的 📋：另發財報分析，卡片留著。"""
    query = update.callback_query
    await query.answer()
    ticker = query.data[len("cearn_"):]
    status = await query.message.reply_text(f"⏳ 正在查詢 {ticker} 財報資料...")
    try:
        result = await _run_earnings_analysis(ticker)
        await reply_long(query.message, result)
        await status.delete()
    except ValueError as e:
        await status.edit_text(f"❌ {e}")
    except Exception as e:
        logger.error("card earnings failed for %s: %s", ticker, e, exc_info=True)
        await status.edit_text("❌ 分析失敗，請稍後再試")


@restrict_callback
async def card_watch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """卡片的 👀：加入自選，卡片留著。"""
    query = update.callback_query
    parts = query.data[len("cadd_"):].split("_", 1)
    ticker = parts[0]
    name = parts[1] if len(parts) > 1 else ticker
    if add_ticker(query.from_user.id, ticker, name):
        await query.answer("已加入追蹤")
        label = f"{name}({ticker})" if name and name != ticker else ticker
        await query.message.reply_text(f"✅ 已加入追蹤：{label}")
    else:
        await query.answer("已在追蹤清單中", show_alert=False)


@restrict_callback
async def alert_hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """卡片的 🔔 按鈕：兩段式追問條件，回覆即設定。"""
    query = update.callback_query
    await query.answer()
    ticker = query.data[len("ahint_"):]
    await ask_alert_condition(query.message, context, ticker)


def build_card_handlers(auth_filter):
    """注意：text handler 必須註冊在 /finance ConversationHandler 之後。"""
    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND & auth_filter, text_lookup_handler),
        CallbackQueryHandler(card_open_callback, pattern="^card_"),
        CallbackQueryHandler(card_analyze_callback, pattern="^cana_"),
        CallbackQueryHandler(card_earnings_callback, pattern="^cearn_"),
        CallbackQueryHandler(card_watch_callback, pattern="^cadd_"),
        CallbackQueryHandler(alert_hint_callback, pattern="^ahint_"),
    ]
