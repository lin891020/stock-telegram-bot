import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.handlers.pending import ask, register
from bot.services.charts import render_chart, PERIODS
from bot.services.stock import looks_like_ticker, is_taiwan_stock
from bot.services.tw_stocks import get_tw_name

logger = logging.getLogger(__name__)

_USAGE = (
    "用法：/chart <代號> [期間]\n"
    "/chart 2330\n/chart NVDA 1y\n\n"
    f"期間：{'、'.join(PERIODS)}（預設 6m）\n"
    "圖表：日 K + 成交量 + MA20/60"
)


def _period_keyboard(ticker: str, current: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"✓{p}" if p == current else p,
            callback_data=f"chartp_{ticker}_{p}",
        )
        for p in PERIODS
    ]])


def _caption(ticker: str, name: str, period: str) -> str:
    label = f"{name}({ticker})" if name else ticker
    return f"{label} {PERIODS[period][2]}走勢"


async def _render(ticker: str, period: str) -> tuple:
    """Returns (png_bytes_or_None, name)."""
    name = (get_tw_name(ticker) or "") if is_taiwan_stock(ticker) else ""
    png = await asyncio.to_thread(render_chart, ticker, period, name)
    return png, name


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await ask(
            update.message, context, "chart",
            "輸入股票代號（可加期間 1m/3m/6m/1y，例：2330 1y）：",
        )
        return

    ticker = context.args[0].upper().strip()
    period = context.args[1].lower().strip() if len(context.args) > 1 else "6m"

    if not looks_like_ticker(ticker):
        await update.message.reply_text(f"「{ticker}」不像股票代號。\n\n{_USAGE}")
        return
    if period not in PERIODS:
        await update.message.reply_text(f"不支援的期間「{period}」。\n\n{_USAGE}")
        return

    await update.message.reply_text(f"⏳ 正在繪製 {ticker} 走勢圖...")

    try:
        png, name = await _render(ticker, period)
    except Exception as e:
        logger.error("chart render failed for %s: %s", ticker, e, exc_info=True)
        await update.message.reply_text("❌ 圖表繪製失敗，請稍後再試")
        return

    if not png:
        await update.message.reply_text(f"查無 {ticker} 的歷史資料，請確認代號是否正確")
        return

    await update.message.reply_photo(
        photo=png,
        caption=_caption(ticker, name, period),
        reply_markup=_period_keyboard(ticker, period),
    )


@restrict_callback
async def chart_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """期間切換按鈕；也作為股票卡片上的「K線」入口。"""
    query = update.callback_query
    await query.answer("繪製中...")

    payload = query.data[len("chartp_"):]
    ticker, _, period = payload.rpartition("_")
    if not ticker or period not in PERIODS:
        return

    try:
        png, name = await _render(ticker, period)
    except Exception as e:
        logger.error("chart render failed for %s: %s", ticker, e, exc_info=True)
        await query.message.reply_text("❌ 圖表繪製失敗，請稍後再試")
        return

    if not png:
        await query.message.reply_text(f"查無 {ticker} 的歷史資料")
        return

    caption = _caption(ticker, name, period)
    keyboard = _period_keyboard(ticker, period)
    if query.message.photo:
        # 已是圖表訊息 → 原地換圖
        await query.message.edit_media(
            InputMediaPhoto(media=png, caption=caption), reply_markup=keyboard
        )
    else:
        # 從股票卡片進來 → 另發一張圖
        await query.message.reply_photo(photo=png, caption=caption, reply_markup=keyboard)


@register("chart")
async def _pending_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await chart_command(update, context)


def build_chart_handler(auth_filter):
    return [
        CommandHandler("chart", chart_command, filters=auth_filter),
        CallbackQueryHandler(chart_period_callback, pattern="^chartp_"),
    ]
