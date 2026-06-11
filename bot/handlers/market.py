import logging
from datetime import date
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.services.market import fetch_market_summary

logger = logging.getLogger(__name__)


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ 查詢大盤中...")
    try:
        summary = await fetch_market_summary()
        today = date.today().strftime("%Y/%m/%d")
        await update.message.reply_text(f"🌐 大盤速覽 {today}\n\n{summary}")
    except Exception as e:
        logger.error("market_command failed: %s", e, exc_info=True)
        await update.message.reply_text("❌ 大盤資料查詢失敗，請稍後再試")


def build_market_handler(auth_filter):
    return CommandHandler("market", market_command, filters=auth_filter)
