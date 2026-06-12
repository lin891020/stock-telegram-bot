from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler

from bot.auth import restrict_callback
from bot.services.recent import get_recent

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []

    recent = get_recent()
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
/earnings TSLA — 財報速覽：近 4 季 EPS beat/miss + LLM 分析
/price TSLA 2330 — 快速查看股價（支援多支）
/chart 2330 6m — 日 K 線圖（成交量 + MA20/60）
/market — 大盤速覽（加權、美股三大、費半、台幣）

自選股與提醒
/watch 2330 — 加入追蹤清單（支援公司名稱）
/watchlist — 查看追蹤清單（點 ❌ 移除）
/alert 2330 >1100 — 到價提醒（也支援 +5% / -5%）
/news — 立即查看追蹤股票新聞

自動推播
• 起床報（隔夜美股 + 大盤 + 財報日 + 重點新聞）— 預設 06:30
• 台股收盤速報 — 預設 14:00
• 自選股財報公布當天自動推送分析

學習與教練
/learn ETF — 學習投資知識
/finance — 個人財務教練（對話式）

設定
/settime 06:30 — 起床報時間；/settime tw 14:30 — 台股收盤速報
/model — 切換 AI 模型（重啟後保留）
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
        await query.message.reply_text("請輸入股票代號：\n/analyze 2330\n/analyze TSLA")
    elif data == "menu_finance":
        await query.message.reply_text("輸入 /finance 開始個人理財教練")
    elif data == "menu_learn":
        await query.message.reply_text("輸入 /learn <主題>，例如：\n/learn ETF\n/learn 緊急備用金")
