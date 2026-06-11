import functools
from telegram import Update
from telegram.ext import ContextTypes, filters as tg_filters
from bot.config import ALLOWED_TELEGRAM_ID

def build_auth_filter():
    """Returns a filter that only passes messages from the allowed Telegram user."""
    return tg_filters.User(user_id=ALLOWED_TELEGRAM_ID)


def restrict_callback(func):
    """Reject callback queries from anyone other than the allowed user.

    CommandHandler supports user filters but CallbackQueryHandler does not,
    so button callbacks need this explicit check.
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query and query.from_user.id != ALLOWED_TELEGRAM_ID:
            await query.answer()
            return None
        return await func(update, context)
    return wrapper
