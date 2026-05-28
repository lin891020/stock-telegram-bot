import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
