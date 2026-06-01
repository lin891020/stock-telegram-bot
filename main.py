import logging
import datetime
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler, help_handler
from bot.handlers.analyze import build_analyze_handler
from bot.handlers.learn import build_learn_handler
from bot.handlers.finance import build_finance_handler
from bot.handlers.model import build_model_handler
from bot.handlers.watch import build_watch_handler, send_daily_news, send_tw_closing, send_us_closing
from bot.handlers.price import build_price_handler
from bot.handlers.earnings import build_earnings_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

async def _post_init(application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start",     "開始使用 / 主選單"),
        BotCommand("analyze",   "📊 深度股票分析報告"),
        BotCommand("earnings",  "📋 財報 EPS 速覽"),
        BotCommand("price",     "💹 快速查看股價"),
        BotCommand("watch",     "👀 新增自選股追蹤"),
        BotCommand("watchlist", "📌 查看自選股（點 ❌ 移除）"),
        BotCommand("news",      "📰 立即查看追蹤股票新聞"),
        BotCommand("learn",     "📚 學習投資觀念"),
        BotCommand("finance",   "💰 個人財務教練"),
        BotCommand("model",     "🤖 切換 AI 模型"),
        BotCommand("help",      "❓ 使用說明"),
    ])


def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CommandHandler("help", help_handler, filters=auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    for handler in build_analyze_handler(auth):
        app.add_handler(handler)

    app.add_handler(build_learn_handler(auth))
    app.add_handler(build_finance_handler(auth))

    for handler in build_model_handler(auth):
        app.add_handler(handler)

    app.add_handler(build_price_handler(auth))

    for handler in build_watch_handler(auth):
        app.add_handler(handler)

    for handler in build_earnings_handler(auth):
        app.add_handler(handler)

    # 晨報 08:00 Taipei = 00:00 UTC
    app.job_queue.run_daily(
        send_daily_news,
        time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc),
    )
    # 台股收盤速報 14:00 Taipei = 06:00 UTC
    app.job_queue.run_daily(
        send_tw_closing,
        time=datetime.time(hour=6, minute=0, tzinfo=datetime.timezone.utc),
    )
    # 美股收盤速報 06:00 Taipei = 22:00 UTC (前一天)
    app.job_queue.run_daily(
        send_us_closing,
        time=datetime.time(hour=22, minute=0, tzinfo=datetime.timezone.utc),
    )

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
