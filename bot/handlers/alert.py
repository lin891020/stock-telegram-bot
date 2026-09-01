import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.services.formatting import change_str, money, name_label
from bot.handlers.pending import ask, register
from bot.services.alerts import (
    parse_condition, describe_condition, condition_text, is_triggered,
    get_alerts, add_alert, remove_alert, all_alerts,
)
from bot.services.big_moves import classify_move, mark_sent, was_sent
from bot.services.stock import intraday_quote, is_taiwan_stock, looks_like_ticker
from bot.services.tw_stocks import get_tw_name
from bot.services.watchlist import iter_watchlists

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
    display = name_label(ticker, name)
    return f"{display} {describe_condition(alert)}"


def _push_text(icon: str, headline: str, ticker: str, price: float, prev,
               tail: str = "", footer: str = "") -> str:
    """提醒推播的統一版面。

    價格放**第一行**：Telegram 的通知橫幅只顯示前一兩行，價格擺在
    第二行的話，你得點進 app 才知道多少錢、值不值得理它。

    數字本身走 formatting.price_with_change，跟報價卡片、晨報、收盤
    速報同一份實作——以前三處各寫一份，同一支股票長成三個樣子。
    """
    market = "TW" if is_taiwan_stock(ticker) else "US"
    lines = [f"{icon} {headline}　{money(price, market)}"]
    change = change_str(price, prev)
    if change or tail:
        lines.append(f"{change}{tail}")
    if footer:
        lines.append(footer)
    return "\n".join(lines)


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
            *[intraday_quote(t) for t in tickers]
        )
        quote_map = dict(zip(tickers, quotes))

        for user_id_str, alert in active:
            price, prev = quote_map.get(alert["ticker"], (None, None))
            if price is None or not is_triggered(alert, price, prev):
                continue
            try:
                rearm = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔄 再設一次相同提醒",
                    callback_data=f"arearm_{alert['ticker']}|{condition_text(alert)}",
                )]])
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=_push_text(
                        "🔔", _alert_label(alert), alert["ticker"], price, prev,
                        footer="此提醒已自動移除",
                    ),
                    reply_markup=rearm,
                )
                remove_alert(int(user_id_str), alert["id"])
            except Exception as e:
                logger.error("alert push failed for %s: %s", alert["ticker"], e, exc_info=True)
    except Exception as e:
        logger.error("check_alerts failed: %s", e, exc_info=True)


def _watchlist_targets(tw_open: bool, us_open: bool) -> list[tuple[str, str, str]]:
    """(user_id_str, ticker, name)：自選股中所屬市場正在交易的標的。"""
    targets = []
    for user_id_str, items in iter_watchlists():
        for ticker, name in items.items():
            if tw_open if is_taiwan_stock(ticker) else us_open:
                targets.append((user_id_str, ticker, name or ticker))
    return targets


async def check_big_moves(context: ContextTypes.DEFAULT_TYPE) -> None:
    """每 10 分鐘執行：自選股台股漲跌停、美股單日 ±10% 自動推播。

    不需要 /alert 設定，加入自選股就會盯。同一天同一支同方向只推一次。
    """
    try:
        taipei_now = datetime.now(timezone.utc) + timedelta(hours=_TAIPEI_UTC_OFFSET)
        tw_open = _tw_market_open(taipei_now)
        us_open = _us_market_open(taipei_now)
        if not tw_open and not us_open:
            return

        targets = _watchlist_targets(tw_open, us_open)
        if not targets:
            return

        tickers = sorted({t for _, t, _ in targets})
        quotes = await asyncio.gather(
            *[intraday_quote(t) for t in tickers]
        )
        quote_map = dict(zip(tickers, quotes))

        for user_id_str, ticker, name in targets:
            price, prev = quote_map.get(ticker, (None, None))
            move = classify_move(ticker, price, prev)
            if move is None or was_sent(user_id_str, ticker, move["direction"]):
                continue
            try:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
                    text=_push_text(
                        "🚨",
                        f"{name_label(ticker, name)} {move['headline']}",
                        ticker, price, prev,
                        tail=f"　前收 {prev:,.2f}" if prev else "",
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 查看", callback_data=f"card_{ticker}")
                    ]]),
                )
                mark_sent(user_id_str, ticker, move["direction"])
            except Exception as e:
                logger.error("big move push failed for %s: %s", ticker, e, exc_info=True)
    except Exception as e:
        logger.error("check_big_moves failed: %s", e, exc_info=True)


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
