import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.services.watchlist import get_watchlist, add_ticker, remove_ticker, _load
from bot.services.news import fetch_and_summarize
from bot.services.stock import looks_like_ticker

logger = logging.getLogger(__name__)


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        tickers = get_watchlist(user_id)
        if not tickers:
            await update.message.reply_text(
                "追蹤清單是空的。\n\n新增：/watch 2330\n移除：/unwatch 2330\n手動查看：/news"
            )
        else:
            lines = "\n".join(f"• {t}" for t in tickers)
            await update.message.reply_text(f"📋 追蹤清單：\n{lines}\n\n移除：/unwatch <代號>")
        return

    ticker = context.args[0].strip().upper()
    if not looks_like_ticker(ticker):
        await update.message.reply_text(f"「{ticker}」不像股票代號，請確認後再試")
        return

    if add_ticker(user_id, ticker):
        await update.message.reply_text(f"✅ 已加入追蹤：{ticker}\n\n每天早上 8 點會自動推送晨報")
    else:
        await update.message.reply_text(f"「{ticker}」已在追蹤清單中")


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("請輸入要移除的代號，例如：/unwatch 2330")
        return

    ticker = context.args[0].strip().upper()
    if remove_ticker(user_id, ticker):
        await update.message.reply_text(f"✅ 已移除追蹤：{ticker}")
    else:
        await update.message.reply_text(f"「{ticker}」不在追蹤清單中")


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    tickers = get_watchlist(user_id)

    if not tickers:
        await update.message.reply_text("追蹤清單是空的，請先用 /watch <代號> 加入股票")
        return

    await update.message.reply_text(f"⏳ 正在整理 {', '.join(tickers)} 的最新新聞...")

    try:
        summary = await fetch_and_summarize(tickers)
        await update.message.reply_text(summary)
    except Exception as e:
        logger.error("news_command failed: %s", e, exc_info=True)
        await update.message.reply_text("❌ 新聞抓取失敗，請稍後再試")


async def send_daily_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback — pushes morning digest to all users with a watchlist."""
    all_data = _load()
    for user_id_str, tickers in all_data.items():
        if not tickers:
            continue
        try:
            summary = await fetch_and_summarize(tickers)
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=f"📰 早安！追蹤股票晨報\n\n{summary}",
            )
        except Exception as e:
            logger.error("Daily news failed for user %s: %s", user_id_str, e, exc_info=True)


def build_watch_handler(auth_filter):
    return [
        CommandHandler("watch", watch_command, filters=auth_filter),
        CommandHandler("unwatch", unwatch_command, filters=auth_filter),
        CommandHandler("news", news_command, filters=auth_filter),
    ]
