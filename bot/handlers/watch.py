"""自選股的增刪查：/watch、/unwatch、/watchlist 與它們的按鈕。

只管清單本身。定時推播的內容在 digest.py，推播時間在 schedule.py——
以前三者擠在同一個檔案裡，想改晨報版面得先在三種職責之間找路。

加入的路徑有三條，最後都收斂到 _add_and_reply：
  代號直接加  → /watch 2330
  搜尋單一命中 → /watch 台積電
  搜尋多筆      → 出按鈕，按下去走 wadd_ callback
"""
import asyncio
import logging

import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.auth import restrict_callback
from bot.handlers.messaging import callback_with_name
from bot.handlers.pending import ask, register
from bot.services.formatting import name_label
from bot.services.settings import get_news_time
from bot.services.stock import (
    clean_us_name, get_stock_summary, is_taiwan_stock, looks_like_ticker, search_ticker,
)
from bot.services.tw_stocks import get_tw_name, has_chinese, search_tw_stocks
from bot.services.watchlist import (
    add_ticker, get_watchlist_with_names, remove_ticker,
)

logger = logging.getLogger(__name__)

_MAX_RESULTS = 5


# ── 顯示 ──────────────────────────────────────────────────────────────

def _added_message(label: str) -> str:
    return f"✅ 已加入追蹤：{label}\n\n每天 {get_news_time()} 會自動推送晨報（/settime 可修改時間）"


def _watchlist_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    # 點名稱開股票卡片，點 ❌ 移除
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(name_label(i["ticker"], i["name"]), callback_data=f"card_{i['ticker']}"),
            InlineKeyboardButton("❌", callback_data=f"wdel_{i['ticker']}"),
        ]
        for i in items
    ])


def _display_name(result: dict) -> str:
    """台股用中文名原樣，美股要去掉「, Inc.」這類尾巴。"""
    return result["name"] if is_taiwan_stock(result["symbol"]) else clean_us_name(result["name"])


def _results_keyboard(results: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{_display_name(r)}({r['symbol']})",
            callback_data=callback_with_name(f"wadd_{r['symbol']}_", _display_name(r)),
        )]
        for r in results
    ])


async def _add_and_reply(reply, user_id: int, ticker: str, name: str) -> None:
    """三條加入路徑共用的結尾：加進清單並回話。"""
    label = name_label(ticker, name)
    if add_ticker(user_id, ticker, name):
        await reply(_added_message(label))
    else:
        await reply(f"「{label}」已在追蹤清單中")


# ── 代號解析 ──────────────────────────────────────────────────────────

async def _resolve_tw(ticker: str) -> str | None:
    """台股代號 → 名稱；查無此代號回 None。

    先查本地快取，沒有再打一次報價驗證——快取不保證涵蓋所有上市櫃股票。
    """
    name = get_tw_name(ticker)
    if name:
        return name
    data = await get_stock_summary(ticker)
    return None if data.get("error") else ticker


async def _resolve_us(ticker: str) -> str | None:
    """美股代號 → 名稱；查無此代號回 None（交給名稱搜尋）。"""
    try:
        info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
    except Exception:
        return ticker
    raw_name = info.get("shortName") or info.get("longName")
    if not (info.get("currentPrice") or info.get("regularMarketPrice")) and not raw_name:
        return None
    return clean_us_name(raw_name) if raw_name else ticker


async def _search(query_text: str) -> list[dict]:
    if has_chinese(query_text):
        return search_tw_stocks(query_text, max_results=_MAX_RESULTS)
    return (await asyncio.to_thread(search_ticker, query_text))[:_MAX_RESULTS]


# ── 指令 ──────────────────────────────────────────────────────────────

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    reply = update.message.reply_text

    if not context.args:
        await ask(update.message, context, "watch", "輸入要加入追蹤的代號或名稱：")
        return

    query_text = " ".join(context.args).strip()

    if looks_like_ticker(query_text):
        ticker = query_text.upper()
        name = await (_resolve_tw(ticker) if is_taiwan_stock(ticker) else _resolve_us(ticker))
        if name is not None:
            await _add_and_reply(reply, user_id, ticker, name)
            return
        if is_taiwan_stock(ticker):
            await reply(f"找不到台股代號「{ticker}」，請確認是否正確")
            return
        # 美股代號查無此檔 → 當成公司名稱再搜一次
    else:
        await reply(f"搜尋「{query_text}」中...")

    results = await _search(query_text)
    if not results:
        await reply(f"找不到「{query_text}」，請確認股票代號或名稱是否正確")
        return
    if len(results) == 1:
        r = results[0]
        await _add_and_reply(reply, user_id, r["symbol"], _display_name(r))
        return
    await reply("找到以下結果，請選擇：", reply_markup=_results_keyboard(results))


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await ask(update.message, context, "unwatch", "輸入要移除的股票代號：")
        return

    ticker = context.args[0].upper().strip()
    if remove_ticker(user_id, ticker):
        await update.message.reply_text(f"✅ 已從追蹤清單移除：{ticker}")
    else:
        await update.message.reply_text(f"「{ticker}」不在追蹤清單中")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = get_watchlist_with_names(update.effective_user.id)
    if not items:
        await update.message.reply_text(
            "追蹤清單是空的。\n\n新增：/watch 2330 或 /watch 台積電\n移除：/unwatch 2330"
        )
        return
    await update.message.reply_text(
        "📋 追蹤清單（點 ❌ 移除）：", reply_markup=_watchlist_keyboard(items)
    )


# ── 按鈕 ──────────────────────────────────────────────────────────────

@restrict_callback
async def watch_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data[len("wadd_"):].split("_", 1)
    ticker = parts[0]
    raw_name = parts[1] if len(parts) > 1 else ticker
    name = raw_name if is_taiwan_stock(ticker) else clean_us_name(raw_name)

    await _add_and_reply(query.edit_message_text, query.from_user.id, ticker, name)


@restrict_callback
async def watch_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    remove_ticker(user_id, query.data[len("wdel_"):])

    items = get_watchlist_with_names(user_id)
    if not items:
        await query.edit_message_text("📋 追蹤清單已清空\n\n新增：/watch 2330 或 /watch 台積電")
        return
    await query.edit_message_reply_markup(reply_markup=_watchlist_keyboard(items))


# ── 兩段式輸入（指令不帶參數時的追問）────────────────────────────────

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
        CallbackQueryHandler(watch_add_callback, pattern="^wadd_"),
        CallbackQueryHandler(watch_delete_callback, pattern="^wdel_"),
    ]
