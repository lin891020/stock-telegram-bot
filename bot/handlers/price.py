import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.handlers.pending import ask, register
from bot.services.formatting import quote_line
from bot.services.stock import get_stock_summary, looks_like_ticker, search_ticker
from bot.services.tw_stocks import has_chinese, search_tw_stocks

logger = logging.getLogger(__name__)


async def _resolve_symbol(query: str):
    """代號直接用；名稱（中/英）取搜尋第一筆。查不到回 None。"""
    if looks_like_ticker(query):
        return query.upper()
    if has_chinese(query):
        results = search_tw_stocks(query, max_results=1)
    else:
        results = await asyncio.to_thread(search_ticker, query, 1)
    return results[0]["symbol"] if results else None


def _format_price_line(ticker: str, data: dict) -> str:
    return quote_line(ticker, data, multiline=True)


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await ask(update.message, context, "price", "輸入股票代號（可多支，空格分隔）：")
        return

    queries = [a.strip() for a in context.args if a.strip()]
    resolved = await asyncio.gather(*[_resolve_symbol(q) for q in queries])

    not_found = [q for q, t in zip(queries, resolved) if t is None]
    tickers = [t for t in resolved if t]
    if not tickers:
        await update.message.reply_text(f"找不到「{'、'.join(not_found)}」，請確認代號或名稱")
        return

    await update.message.reply_text(f"⏳ 查詢 {', '.join(tickers)} 中...")

    results = await asyncio.gather(*[get_stock_summary(t) for t in tickers])

    lines = []
    for t, data in zip(tickers, results):
        if not isinstance(data, dict) or data.get("error"):
            lines.append(f"{t}：查無資料")
        else:
            lines.append(_format_price_line(t, data))

    if not_found:
        lines.append(f"（找不到：{'、'.join(not_found)}）")

    await update.message.reply_text("\n\n".join(lines))


@register("price")
async def _pending_price(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await price_command(update, context)


def build_price_handler(auth_filter):
    return CommandHandler("price", price_command, filters=auth_filter)
