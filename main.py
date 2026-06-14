import asyncio
import logging
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler, help_handler
from bot.handlers.analyze import build_analyze_handler
from bot.handlers.learn import build_learn_handler
from bot.handlers.finance import build_finance_handler
from bot.handlers.model import build_model_handler
from bot.handlers.watch import (
    build_watch_handler,
    schedule_daily_news,
    schedule_tw_closing,
)
from bot.handlers.price import build_price_handler
from bot.handlers.alert import build_alert_handler, check_alerts
from bot.handlers.card import build_card_handlers
from bot.handlers.market import build_market_handler
from bot.handlers.chart import build_chart_handler
from bot.handlers.health import build_health_handler
from bot.services.tw_stocks import load_tw_stock_list
from bot.handlers.earnings import build_earnings_handler, poll_earnings_announcements

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

async def _post_init(application) -> None:
    await asyncio.to_thread(load_tw_stock_list)
    await application.bot.set_my_commands([
        BotCommand("start",     "開始使用 / 主選單"),
        BotCommand("analyze",   "📊 深度股票分析報告"),
        BotCommand("earnings",  "📋 財報 EPS 速覽"),
        BotCommand("price",     "💹 快速查看股價"),
        BotCommand("chart",     "📈 股價 K 線圖"),
        BotCommand("market",    "🌐 大盤速覽"),
        BotCommand("watch",     "👀 新增自選股追蹤"),
        BotCommand("watchlist", "📌 查看自選股（點 ❌ 移除）"),
        BotCommand("alert",     "🔔 價格到價提醒"),
        BotCommand("news",      "📰 立即查看追蹤股票新聞"),
        BotCommand("settime",   "⏰ 設定推送時間"),
        BotCommand("learn",     "📚 學習投資觀念"),
        BotCommand("finance",   "💰 個人財務教練"),
        BotCommand("model",     "🤖 切換 AI 模型"),
        BotCommand("health",    "🩺 檢查資料源狀態"),
        BotCommand("help",      "❓ 使用說明"),
    ])


def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CommandHandler("help", help_handler, filters=auth))
    app.add_handler(build_health_handler(auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    for handler in build_analyze_handler(auth):
        app.add_handler(handler)

    for handler in build_learn_handler(auth):
        app.add_handler(handler)

    app.add_handler(build_finance_handler(auth))

    for handler in build_model_handler(auth):
        app.add_handler(handler)

    app.add_handler(build_price_handler(auth))
    app.add_handler(build_market_handler(auth))

    for handler in build_chart_handler(auth):
        app.add_handler(handler)

    for handler in build_watch_handler(auth):
        app.add_handler(handler)

    for handler in build_earnings_handler(auth):
        app.add_handler(handler)

    for handler in build_alert_handler(auth):
        app.add_handler(handler)

    # 股票卡片：純文字查詢必須註冊在 /finance ConversationHandler 之後，
    # 對話進行中的文字輸入才會先被對話流程吃掉
    for handler in build_card_handlers(auth):
        app.add_handler(handler)

    # 推送時間皆由 /settime 設定（存於 data/settings.json）
    # 預設：起床報 06:30（含隔夜美股收盤）、台股收盤 14:00（皆台北時間）
    schedule_daily_news(app.job_queue)
    schedule_tw_closing(app.job_queue)

    # 價格提醒：每 10 分鐘檢查（盤中才打 API）
    app.job_queue.run_repeating(check_alerts, interval=600, first=60, name="alert_check")
    # 財報公布偵測：每 30 分鐘輪詢（無 pending 直接 return）
    app.job_queue.run_repeating(poll_earnings_announcements, interval=1800, first=300, name="earnings_poll")

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
