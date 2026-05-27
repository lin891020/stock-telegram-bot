from telegram.ext import filters as tg_filters
from bot.config import ALLOWED_TELEGRAM_ID

def build_auth_filter():
    """Returns a filter that only passes messages from the allowed Telegram user."""
    return tg_filters.User(user_id=ALLOWED_TELEGRAM_ID)
