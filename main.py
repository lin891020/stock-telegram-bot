import asyncio
import logging
from datetime import time as dt_time, timezone
from telegram import BotCommand
from telegram.ext import (
    AIORateLimiter, Application, CallbackQueryHandler, CommandHandler,
    MessageHandler, PicklePersistence, filters,
)

from pathlib import Path

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import (
    start_handler, menu_callback_handler, help_handler, cancel_handler,
)
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
from bot.handlers.alert import build_alert_handler, check_alerts, check_big_moves
from bot.handlers.card import build_card_handlers
from bot.handlers.market import build_market_handler
from bot.handlers.chart import build_chart_handler
from bot.handlers.errors import error_handler
from bot.handlers.pending import drop_stale_pending
from bot.handlers.health import build_health_handler, health_watchdog
from bot.services.tw_stocks import load_tw_stock_list
from bot.handlers.earnings import build_earnings_handler, poll_earnings_announcements

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# httpx 的 INFO log 會把完整請求 URL 印出來，Telegram 的 URL 裡就含 bot token，
# 等於把 token 明文寫進 journalctl。調到 WARNING 才能安全地把 log 給別人看。
logging.getLogger("httpx").setLevel(logging.WARNING)

_PERSISTENCE_FILE = Path("data/ptb_state.pickle")

# VM 跑 UTC，排程時間一律照既有慣例明確換算（見 watch.py 的 _TAIPEI_UTC_OFFSET）
_TAIPEI_UTC_OFFSET = 8


def _taipei(hour: int, minute: int = 0) -> dt_time:
    return dt_time(hour=(hour - _TAIPEI_UTC_OFFSET) % 24, minute=minute, tzinfo=timezone.utc)

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
        BotCommand("cancel",    "✖️ 取消目前操作"),
        BotCommand("help",      "❓ 使用說明"),
    ])


def main() -> None:
    auth = build_auth_filter()
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        # 預設是「一次處理一個 update」——/analyze 跑 30-60 秒期間，
        # 你打任何指令都不是變慢，是排在後面等。
        # ⚠️ /finance 是 ConversationHandler，官方建議並行時要小心；
        # 單使用者情境不會同時走兩條對話，風險可接受。
        .concurrent_updates(True)
        # 晨報一次會送好幾則（send_long 切段），主動節流避免撞上 Telegram 限速
        .rate_limiter(AIORateLimiter())
        # user_data 存磁碟：/finance 五階段問卷、pending 追問都在裡面，
        # 而我們的部署流程就是 ssh + restart，不存就是每次部署都清空
        .persistence(PicklePersistence(filepath=str(_PERSISTENCE_FILE)))
        .build()
    )

    # 所有 handler 都沒接住的例外最後由這裡兜底，避免「訊息就是沒來」
    app.add_error_handler(error_handler)

    # group -1 先跑：任何指令都先丟掉等待中的追問。
    # 否則「/watch → 改用 /price → 之後打『台積電』」會被 watch 的
    # pending 吃掉，變成加入自選股而不是查卡片。
    app.add_handler(
        MessageHandler(filters.COMMAND & auth, drop_stale_pending), group=-1
    )

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

    # 註冊在 finance 的 ConversationHandler 之後：對話進行中的 /cancel
    # 會先被對話的 fallback 接走，其餘情況才落到這個全域取消
    app.add_handler(CommandHandler("cancel", cancel_handler, filters=auth))

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
    # 自選股異常波動：台股漲跌停、美股單日 ±10%，盤中每 10 分鐘檢查
    app.job_queue.run_repeating(check_big_moves, interval=600, first=90, name="big_move_check")
    # 財報公布偵測：每小時掃所有自選股（要打 yfinance，不宜太密）
    app.job_queue.run_repeating(poll_earnings_announcements, interval=3600, first=120, name="earnings_poll")
    # 每日巡檢：七項檢查有紅燈才推播，全綠時安靜。
    # /health 要「想到去打」才會知道，但沒人會沒事去打它——lxml 那次
    # 就是這樣靜靜壞了兩個月。
    # 排在晨報（06:30）之前：真的有東西壞了，你會在讀報告的同時就知道
    app.job_queue.run_daily(health_watchdog, time=_taipei(6, 0), name="health_watchdog")

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
