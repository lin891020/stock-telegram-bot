from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📈 分析股票", callback_data="menu_analyze")],
        [InlineKeyboardButton("💰 個人理財教練", callback_data="menu_finance")],
        [InlineKeyboardButton("📚 學習投資知識", callback_data="menu_learn")],
    ]
    await update.message.reply_text(
        "嗨！我是你的投資助理 👋\n\n"
        "你可以直接輸入指令，或點選以下功能：\n\n"
        "• /analyze 2330 — 分析台積電\n"
        "• /analyze TSLA — 分析特斯拉\n"
        "• /finance — 個人理財教練\n"
        "• /learn ETF — 學習投資知識",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

_HELP_TEXT = """\
📋 所有可用指令

股票分析
/analyze 2330 — 台股/美股深度分析（7 種類型）
/earnings TSLA — 財報速覽：近 4 季 EPS beat/miss + LLM 分析

新聞晨報
/watch 2330 — 加入追蹤清單
/unwatch 2330 — 移除追蹤
/watch — 查看目前追蹤清單
/news — 立即查看追蹤股票新聞（每天早上 8 點也會自動推送）

學習與教練
/learn ETF — 學習投資知識
/finance — 個人理財教練（對話式）

設定
/model — 切換 AI 模型
/help — 顯示此說明
"""

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_HELP_TEXT)


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
