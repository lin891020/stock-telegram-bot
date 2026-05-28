from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

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
