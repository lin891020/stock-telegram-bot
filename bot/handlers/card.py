"""股票卡片：直接傳代號或名稱（不用指令）就回報價卡片＋操作按鈕。

按鈕直接重用既有 callback：apick_（分析類型選單）、epick_（財報分析）、
wadd_（加自選）、chartp_（K 線，chart.py）。
"""
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters

from bot.auth import restrict_callback
from bot.services.recent import add_recent
from bot.services.stock import (
    get_stock_summary, looks_like_ticker, search_ticker, is_taiwan_stock, clean_us_name,
)
from bot.services.tw_stocks import has_chinese, search_tw_stocks

logger = logging.getLogger(__name__)

_MAX_QUERY_LEN = 20  # 超過就當聊天雜訊，不回應


def _card_keyboard(ticker: str, name: str) -> InlineKeyboardMarkup:
    wadd_prefix = f"wadd_{ticker}_"
    budget = 64 - len(wadd_prefix.encode("utf-8"))
    safe_name = (name or ticker).encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 深度分析", callback_data=f"apick_{ticker}"),
            InlineKeyboardButton("📈 K線", callback_data=f"chartp_{ticker}_6m"),
        ],
        [
            InlineKeyboardButton("📋 財報", callback_data=f"epick_{ticker}"),
            InlineKeyboardButton("🔔 設提醒", callback_data=f"ahint_{ticker}"),
        ],
        [InlineKeyboardButton("👀 加自選", callback_data=wadd_prefix + safe_name)],
    ])


def _card_text(ticker: str, data: dict) -> str:
    name = data.get("name", "")
    label = f"{name}({ticker})" if name and name != ticker else ticker
    price = data.get("price") or data.get("close")
    if not price:
        return f"{label}\n無報價資料"
    prev = data.get("prev_close")
    currency = "元" if data.get("market") == "TW" else "USD"
    line = f"{label}\n{price:,.2f} {currency}"
    if prev:
        pct = (price - prev) / prev * 100
        arrow = "▲" if pct >= 0 else "▼"
        sign = "+" if pct >= 0 else ""
        line += f"  {arrow} {sign}{pct:.2f}%（{sign}{price - prev:.2f}）"
    return line


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
    """純文字（非指令）：代號直接出卡片，名稱先搜尋。"""
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
async def alert_hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    ticker = query.data[len("ahint_"):]
    await query.message.reply_text(
        f"設定 {ticker} 的價格提醒，直接輸入：\n\n"
        f"/alert {ticker} >1100 — 漲破 1100\n"
        f"/alert {ticker} <950 — 跌破 950\n"
        f"/alert {ticker} +5% — 單日漲 5%\n"
        f"/alert {ticker} -5% — 單日跌 5%"
    )


def build_card_handlers(auth_filter):
    """注意：text handler 必須註冊在 /finance ConversationHandler 之後。"""
    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND & auth_filter, text_lookup_handler),
        CallbackQueryHandler(card_open_callback, pattern="^card_"),
        CallbackQueryHandler(alert_hint_callback, pattern="^ahint_"),
    ]
