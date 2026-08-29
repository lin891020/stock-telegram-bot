from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.auth import restrict_callback
from bot.handlers.learn import _topics_keyboard, _load_lessons
from bot.handlers.pending import ask, clear_pending
from bot.services.recent import get_recent

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []

    recent = get_recent(update.effective_user.id)
    if recent:
        keyboard.append([
            InlineKeyboardButton(
                i["name"] if i["name"] != i["ticker"] else i["ticker"],
                callback_data=f"card_{i['ticker']}",
            )
            for i in recent[:3]
        ])

    keyboard += [
        [InlineKeyboardButton("📈 分析股票", callback_data="menu_analyze")],
        [InlineKeyboardButton("💰 個人理財教練", callback_data="menu_finance")],
        [InlineKeyboardButton("📚 學習投資知識", callback_data="menu_learn")],
    ]
    recent_hint = "最近查過（點了直接看）＋" if recent else ""
    await update.message.reply_text(
        "嗨！我是你的投資助理 👋\n\n"
        "💡 直接傳股票代號或名稱就能查，例如：2330、台積電、NVDA\n\n"
        f"{recent_hint}常用功能：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

_HELP_TEXT = """\
📋 使用說明

💡 最快的用法：直接傳代號或名稱
傳「2330」「台積電」「NVDA」就會回報價卡片，
按鈕直接做深度分析、K線、財報、提醒、加自選。
指令不帶參數也沒關係——bot 會追問你，回覆即可。

股票分析
/analyze 2330 — 台股/美股深度分析（7 種類型）
/earnings TSLA — 財報速覽：營收/獲利/管理層說法/官方財測，可出完整 PDF
/price TSLA 2330 — 快速查看股價（支援多支）
/chart 2330 6m — 日 K 線圖（成交量 + MA20/60）
/market — 大盤速覽（加權、美股三大、費半、台幣）

自選股與提醒
/watch 2330 — 加入追蹤清單（支援公司名稱）
/watchlist — 查看追蹤清單（點 ❌ 移除）
/alert 2330 >1100 — 到價提醒（也支援 +5% / -5%）
/news — 立即查看追蹤股票新聞

自動推播
• 起床報（隔夜美股 + 大盤 + 財報日 + 新聞標題）— 預設 06:30
• 台股收盤速報 — 預設 14:00
• 自選台股漲跌停、美股單日 ±10% — 盤中每 10 分鐘
• 自選股財報公布 — 自動推速覽，按鈕出完整報告
• 每天 06:00 系統巡檢 — 只有壞掉才通知你

學習與教練
/learn ETF — 學習投資知識
/finance — 個人財務教練（對話式）

設定
/settime 06:30 — 起床報時間；/settime tw 14:30 — 台股收盤速報
/model — 切換 AI 模型（重啟後保留）
/health — 檢查 yfinance / 台股 / AI 是否正常
/help — 顯示此說明
"""

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_HELP_TEXT)


@restrict_callback
async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_analyze":
        # 兩段式：直接追問，回覆代號或名稱即可
        await ask(query.message, context, "analyze", "輸入要分析的股票代號或公司名稱：")
    elif data == "menu_finance":
        await query.message.reply_text("輸入 /finance 開始個人理財教練")
    elif data == "menu_learn":
        await query.message.reply_text(
            "📚 點主題直接看，或輸入 /learn <主題>：",
            reply_markup=_topics_keyboard(_load_lessons()),
        )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """全域取消：清掉等待中的追問。

    /finance 對話中的 /cancel 由 ConversationHandler 的 fallback 先接走，
    走到這裡代表沒有進行中的對話。pending 現在會存到磁碟（跨重啟），
    所以需要一個明確的出口，而不是只能等 180 秒過期。
    """
    if clear_pending(context):
        await update.message.reply_text("已取消。")
    else:
        await update.message.reply_text("目前沒有進行中的操作。")
