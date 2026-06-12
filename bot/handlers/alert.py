import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.handlers.pending import ask, register
from bot.services.alerts import (
    parse_condition, describe_condition, condition_text, is_triggered,
    get_alerts, add_alert, remove_alert, all_alerts,
)
from bot.services.stock import is_taiwan_stock, looks_like_ticker
from bot.services.tw_stocks import get_tw_name

logger = logging.getLogger(__name__)

_TAIPEI_UTC_OFFSET = 8

_USAGE = (
    "用法：\n"
    "/alert 2330 >1100 — 漲破 1100 提醒\n"
    "/alert 2330 <950 — 跌破 950 提醒\n"
    "/alert NVDA +5% — 單日漲 5% 提醒\n"
    "/alert NVDA -5% — 單日跌 5% 提醒\n"
    "/alert — 查看所有提醒（點 ❌ 移除）\n\n"
    "盤中每 10 分鐘檢查一次，觸發後自動移除。"
)


def _alert_label(alert: dict) -> str:
    ticker = alert["ticker"]
    name = get_tw_name(ticker) if is_taiwan_stock(ticker) else None
    display = f"{name}({ticker})" if name else ticker
    return f"{display} {describe_condition(alert)}"


def _build_alert_keyboard(alerts: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{_alert_label(a)}  ❌", callback_data=f"adel_{a['id']}")]
        for a in alerts
    ])


async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        alerts = get_alerts(user_id)
        if not alerts:
            await update.message.reply_text(f"目前沒有價格提醒。\n\n{_USAGE}")
            return
        await update.message.reply_text(
            "🔔 價格提醒（點 ❌ 移除，觸發後自動移除）：",
            reply_markup=_build_alert_keyboard(alerts),
        )
        return

    ticker = context.args[0].upper().strip()
    if not looks_like_ticker(ticker):
        await update.message.reply_text(f"「{ticker}」不像股票代號。\n\n{_USAGE}")
        return

    if len(context.args) < 2:
        # 只給代號 → 追問條件
        await ask_alert_condition(update.message, context, ticker)
        return

    condition = parse_condition(" ".join(context.args[1:]))
    if condition is None:
        await update.message.reply_text(f"看不懂條件「{' '.join(context.args[1:])}」。\n\n{_USAGE}")
        return

    alert = add_alert(user_id, ticker, condition)
    await update.message.reply_text(
        f"✅ 已設定提醒：{_alert_label(alert)}\n\n盤中每 10 分鐘檢查，觸發後會自動移除"
    )


async def ask_alert_condition(message, context, ticker: str) -> None:
    """兩段式設提醒：追問條件，回覆即設定。卡片的 🔔 按鈕也走這裡。"""
    await ask(
        message, context, "alert",
        f"輸入 {ticker} 的提醒條件：\n>1100（漲破）、<950（跌破）、+5%（單日漲）、-5%（單日跌）",
        ticker=ticker,
    )


@register("alert")
async def _pending_alert(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    ticker = pending.get("ticker", "")
    context.args = ([ticker] if ticker else []) + update.message.text.split()
    await alert_command(update, context)


@restrict_callback
async def alert_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    alert_id = query.data[len("adel_"):]
    user_id = query.from_user.id
    remove_alert(user_id, alert_id)

    alerts = get_alerts(user_id)
    if not alerts:
        await query.edit_message_text("🔔 價格提醒已清空\n\n新增：/alert 2330 >1100")
        return
    await query.edit_message_reply_markup(reply_markup=_build_alert_keyboard(alerts))


def _tw_market_open(taipei_now: datetime) -> bool:
    return taipei_now.weekday() < 5 and time(9, 0) <= taipei_now.time() <= time(13, 40)


def _us_market_open(taipei_now: datetime) -> bool:
    """寬鬆視窗 21:00–05:30 台北時間，涵蓋美國日光節約兩種狀態。"""
    t = taipei_now.time()
    if t >= time(21, 0):
        return taipei_now.weekday() < 5  # 週一到週五晚間開盤
    if t <= time(5, 30):
        return 1 <= taipei_now.weekday() <= 5  # 週二到週六凌晨為前一日美股盤
    return False


def _fetch_quote_sync(ticker: str) -> tuple:
    """Return (last_price, prev_close) or (None, None)."""
    symbol = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker
    try:
        info = yf.Ticker(symbol).fast_info
        return info.last_price, info.previous_close
    except Exception as e:
        logger.warning("alert quote failed for %s: %s", ticker, e)
        return None, None


async def check_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """每 10 分鐘執行：檢查盤中市場的提醒，觸發即推送並移除。"""
    try:
        data = all_alerts()
        if not data:
            return

        taipei_now = datetime.now(timezone.utc) + timedelta(hours=_TAIPEI_UTC_OFFSET)
        tw_open = _tw_market_open(taipei_now)
        us_open = _us_market_open(taipei_now)
        if not tw_open and not us_open:
            return

        def _market_active(ticker: str) -> bool:
            return tw_open if is_taiwan_stock(ticker) else us_open

        active = [
            (user_id_str, a)
            for user_id_str, alerts in data.items()
            for a in alerts
            if _market_active(a["ticker"])
        ]
        if not active:
            return

        tickers = sorted({a["ticker"] for _, a in active})
        quotes = await asyncio.gather(
            *[asyncio.to_thread(_fetch_quote_sync, t) for t in tickers]
        )
        quote_map = dict(zip(tickers, quotes))

        for user_id_str, alert in active:
            price, prev = quote_map.get(alert["ticker"], (None, None))
            if price is None or not is_triggered(alert, price, prev):
                continue
            pct_part = ""
            if prev:
                pct = (price - prev) / prev * 100
                sign = "+" if pct >= 0 else ""
                pct_part = f"（{sign}{pct:.2f}%）"
            try:
                rearm = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔄 再設一次相同提醒",
                    callback_data=f"arearm_{alert['ticker']}|{condition_text(alert)}",
                )]])
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=f"🔔 {_alert_label(alert)}\n現價 {price:.2f}{pct_part}\n\n此提醒已自動移除",
                    reply_markup=rearm,
                )
                remove_alert(int(user_id_str), alert["id"])
            except Exception as e:
                logger.error("alert push failed for %s: %s", alert["ticker"], e, exc_info=True)
    except Exception as e:
        logger.error("check_alerts failed: %s", e, exc_info=True)


@restrict_callback
async def alert_rearm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    payload = query.data[len("arearm_"):]
    ticker, _, cond_text = payload.partition("|")
    condition = parse_condition(cond_text)
    if not ticker or condition is None:
        await query.answer("無法解析提醒條件", show_alert=True)
        return

    alert = add_alert(query.from_user.id, ticker, condition)
    await query.answer("已重新設定")
    await query.edit_message_text(
        f"{query.message.text}\n\n🔄 已重新設定：{_alert_label(alert)}"
    )


def build_alert_handler(auth_filter):
    return [
        CommandHandler("alert", alert_command, filters=auth_filter),
        CallbackQueryHandler(alert_delete_callback, pattern="^adel_"),
        CallbackQueryHandler(alert_rearm_callback, pattern="^arearm_"),
    ]
