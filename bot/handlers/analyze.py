import asyncio
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.services.stock import get_stock_summary, looks_like_ticker, search_ticker
from bot.services.financials import get_financials, format_financials_for_prompt
from bot.services.llm import call_llm
from bot.services.pdf import generate_pdf
from bot.prompts.analysis import PROMPTS, ANALYSIS_BUTTONS

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是一位華爾街資深股票分析師，用繁體中文撰寫專業且深入的分析報告。"
    "分析時引用提供的真實財務數據，結論要有邏輯依據，語氣客觀。"
)


def _analysis_keyboard(ticker: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"analyze_{ticker}_{key}")]
        for label, key in ANALYSIS_BUTTONS
    ])


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "請輸入股票代號或公司名稱，例如：\n"
            "/analyze 2330\n/analyze TSLA\n/analyze Micron"
        )
        return

    query = " ".join(context.args).strip()
    ticker = query.upper()

    if looks_like_ticker(query):
        context.user_data["analyze_ticker"] = ticker
        await update.message.reply_text(
            f"選擇 {ticker} 的分析類型：",
            reply_markup=_analysis_keyboard(ticker),
        )
        return

    # Search by company name
    await update.message.reply_text(f"搜尋「{query}」中...")
    results = await asyncio.to_thread(search_ticker, query)

    if not results:
        await update.message.reply_text(
            f"找不到「{query}」相關的股票。\n請直接輸入股票代號，例如：/analyze MU"
        )
        return

    keyboard = [
        [InlineKeyboardButton(
            f"{r['symbol']} — {r['name'][:30]}",
            callback_data=f"apick_{r['symbol']}",
        )]
        for r in results
    ]
    await update.message.reply_text(
        f"找到以下結果，請選擇：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def analyze_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a ticker from search results."""
    query = update.callback_query
    await query.answer()

    ticker = query.data.replace("apick_", "", 1)
    context.user_data["analyze_ticker"] = ticker
    await query.edit_message_text(
        f"選擇 {ticker} 的分析類型：",
        reply_markup=_analysis_keyboard(ticker),
    )


async def analyze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # callback_data format: analyze_{ticker}_{key}
    parts = query.data[len("analyze_"):].rsplit("_", 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ 無效的操作，請重新使用 /analyze 指令")
        return

    ticker, analysis_key = parts

    if analysis_key not in PROMPTS:
        await query.edit_message_text("❌ 無效的分析類型，請重新使用 /analyze 指令")
        return

    label = next((l for l, k in ANALYSIS_BUTTONS if k == analysis_key), analysis_key)
    await query.edit_message_text(f"⏳ 正在抓取 {ticker} 股價與財務數據...")

    try:
        stock_data, financials = await asyncio.gather(
            get_stock_summary(ticker),
            get_financials(ticker),
        )

        if isinstance(stock_data, dict) and stock_data.get("error"):
            await query.edit_message_text(f"❌ {stock_data['error']}")
            return

        await query.edit_message_text(f"⏳ AI 正在生成 {ticker} — {label} 報告，請稍候...")

        financials_text = format_financials_for_prompt(financials)
        prompt = PROMPTS[analysis_key].format(ticker=ticker)
        current_date = date.today().strftime("%Y年%m月%d日")
        user_msg = f"今天日期：{current_date}\n\n即時股價資料：\n{stock_data}\n\n{financials_text}\n\n{prompt}"

        content = await asyncio.to_thread(call_llm, _SYSTEM, user_msg)

        pdf_bytes = generate_pdf(ticker, label, content)

        today = date.today().strftime("%Y%m%d")
        company_name = stock_data.get("name", "") if isinstance(stock_data, dict) else ""
        from bot.services.stock import is_taiwan_stock
        if is_taiwan_stock(ticker) and company_name:
            filename = f"{ticker}_{company_name}_{today}.pdf"
        else:
            filename = f"{ticker}_{today}.pdf"

        await query.message.reply_document(
            document=pdf_bytes,
            filename=filename,
            caption=f"✅ {ticker} — {label} 分析完成",
        )
        await query.edit_message_text(f"✅ {ticker} {label} 分析完成")

    except Exception as exc:
        logger.error("Analysis failed for %s/%s: %s", ticker, analysis_key, exc, exc_info=True)
        await query.edit_message_text(f"❌ 分析失敗，請稍後再試")


def build_analyze_handler(auth_filter):
    return [
        CommandHandler("analyze", analyze_command, filters=auth_filter),
        CallbackQueryHandler(analyze_pick_callback, pattern="^apick_"),
        CallbackQueryHandler(analyze_callback, pattern="^analyze_"),
    ]
