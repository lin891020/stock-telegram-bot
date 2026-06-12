import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.handlers.pending import ask, register
from bot.services.stock import get_stock_summary

logger = logging.getLogger(__name__)


def _format_price_line(ticker: str, data: dict) -> str:
    price = data.get("price") or data.get("close")
    prev = data.get("prev_close")
    name = data.get("name", "")
    label = f"{name}({ticker})" if name and name != ticker else ticker
    currency = "元" if data.get("market") == "TW" else "USD"

    if not price:
        return f"{label}：無報價"

    if prev and prev != 0:
        change = price - prev
        pct = change / prev * 100
        arrow = "▲" if change >= 0 else "▼"
        sign = "+" if change >= 0 else ""
        return f"{label}\n收 {price:.2f} {currency}  {arrow} {sign}{pct:.2f}%（{sign}{change:.2f}）"

    return f"{label}\n收 {price:.2f} {currency}"


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await ask(update.message, context, "price", "輸入股票代號（可多支，空格分隔）：")
        return

    tickers = [a.upper().strip() for a in context.args]
    await update.message.reply_text(f"⏳ 查詢 {', '.join(tickers)} 中...")

    results = await asyncio.gather(*[get_stock_summary(t) for t in tickers])

    lines = []
    for t, data in zip(tickers, results):
        if not isinstance(data, dict) or data.get("error"):
            lines.append(f"{t}：查無資料")
        else:
            lines.append(_format_price_line(t, data))

    await update.message.reply_text("\n\n".join(lines))


@register("price")
async def _pending_price(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await price_command(update, context)


def build_price_handler(auth_filter):
    return CommandHandler("price", price_command, filters=auth_filter)
