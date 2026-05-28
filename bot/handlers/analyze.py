import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.services.stock import get_stock_summary
from bot.services.llm import call_llm, ANTHROPIC_ANALYSIS_MODEL
from bot.services.pdf import generate_pdf
from bot.prompts.analysis import PROMPTS, ANALYSIS_BUTTONS

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是一位華爾街資深股票分析師，用繁體中文撰寫專業且深入的分析報告。"
    "分析時引用提供的真實財務數據，結論要有邏輯依據，語氣客觀。"
)


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "請輸入股票代號，例如：\n/analyze 2330\n/analyze TSLA"
        )
        return

    ticker = context.args[0].upper().strip()
    context.user_data["analyze_ticker"] = ticker

    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"analyze_{key}")]
        for label, key in ANALYSIS_BUTTONS
    ]
    await update.message.reply_text(
        f"選擇 {ticker} 的分析類型：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def analyze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    analysis_key = query.data.replace("analyze_", "")
    ticker = context.user_data.get("analyze_ticker")

    if not ticker:
        await query.edit_message_text("請先使用 /analyze <代號> 指令")
        return

    label = next((l for l, k in ANALYSIS_BUTTONS if k == analysis_key), analysis_key)
    await query.edit_message_text(f"⏳ 正在分析 {ticker} — {label}，請稍候（約30秒）...")

    try:
        stock_data = await get_stock_summary(ticker)
        prompt = PROMPTS[analysis_key].format(ticker=ticker)
        user_msg = f"股票資料：\n{stock_data}\n\n{prompt}"

        # Run blocking LLM call in thread pool to avoid blocking the event loop
        content = await asyncio.to_thread(call_llm, _SYSTEM, user_msg, ANTHROPIC_ANALYSIS_MODEL)

        pdf_bytes = generate_pdf(ticker, label, content)

        await query.message.reply_document(
            document=pdf_bytes,
            filename=f"{ticker}_{analysis_key}_分析.pdf",
            caption=f"✅ {ticker} — {label} 分析完成",
        )
        await query.edit_message_text(f"✅ {ticker} {label} 分析完成")

    except Exception as exc:
        logger.error("Analysis failed for %s: %s", ticker, exc)
        await query.edit_message_text(f"❌ 分析失敗：{exc}")


def build_analyze_handler(auth_filter):
    return [
        CommandHandler("analyze", analyze_command, filters=auth_filter),
        CallbackQueryHandler(analyze_callback, pattern="^analyze_"),
    ]
