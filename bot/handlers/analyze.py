import asyncio
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.handlers.pending import ask, register
from bot.services.stock import get_stock_summary, looks_like_ticker, search_ticker, is_taiwan_stock, clean_us_name
from bot.services.tw_stocks import has_chinese, search_tw_stocks
from bot.services.financials import get_financials
from bot.services.evidence import build_evidence
from bot.services.metrics import fetch_key_metrics
from bot.services.llm import call_llm
from bot.services.pdf import generate_pdf
from bot.prompts.analysis import PROMPTS, ANALYSIS_BUTTONS

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是一位華爾街資深股票分析師，正在示範如何拆解一家公司給想學會自己看公司的個人投資人。"
    "用繁體中文，語氣客觀。所有數字必須引用提供的真實資料並標註來源，"
    "推理過程比結論重要，不以自己的名義給出買賣評級。"
)


def _extract_brief(content: str) -> str:
    """取出報告開頭的【速覽】區塊（到第一個章節標題為止）。"""
    idx = content.find("【速覽】")
    if idx == -1:
        return ""
    rest = content[idx:]
    stop = rest.find("##")
    brief = rest[:stop] if stop > 0 else rest[:600]
    return brief.replace("**", "").strip()


def _analysis_keyboard(ticker: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"analyze_{ticker}_{key}")]
        for label, key in ANALYSIS_BUTTONS
    ])


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await ask(update.message, context, "analyze", "輸入要分析的股票代號或公司名稱：")
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

    # Search by company name — Chinese goes to the TWSE cache, otherwise yfinance
    await update.message.reply_text(f"搜尋「{query}」中...")
    if has_chinese(query):
        results = search_tw_stocks(query)
    else:
        results = await asyncio.to_thread(search_ticker, query)

    if not results:
        await update.message.reply_text(
            f"找不到「{query}」相關的股票。\n請直接輸入股票代號，例如：/analyze MU"
        )
        return

    def _display_name(r: dict) -> str:
        return r["name"] if is_taiwan_stock(r["symbol"]) else clean_us_name(r["name"])

    keyboard = [
        [InlineKeyboardButton(
            f"{r['symbol']} — {_display_name(r)[:30]}",
            callback_data=f"apick_{r['symbol']}",
        )]
        for r in results
    ]
    await update.message.reply_text(
        "找到以下結果，請選擇：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@restrict_callback
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


@restrict_callback
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
        stock_data, financials, (metrics, anomalies) = await asyncio.gather(
            get_stock_summary(ticker),
            get_financials(ticker),
            fetch_key_metrics(ticker),
        )

        if isinstance(stock_data, dict) and stock_data.get("error"):
            await query.edit_message_text(f"❌ {stock_data['error']}")
            return

        await query.edit_message_text(f"⏳ AI 正在生成 {ticker} — {label} 報告，請稍候...")

        # 證據包負責「有什麼」與「缺什麼」，兩者都由程式決定而非模型自陳
        evidence = build_evidence(ticker, analysis_key, stock_data, financials, metrics, anomalies)
        prompt = PROMPTS[analysis_key].format(ticker=ticker)
        current_date = date.today().strftime("%Y年%m月%d日")
        user_msg = f"今天日期：{current_date}\n\n{evidence.to_prompt()}\n\n{prompt}"
        logger.info(
            "analyze %s/%s: %d 項事實，%d 項缺漏",
            ticker, analysis_key, len(evidence.facts), len(evidence.missing),
        )

        content = await asyncio.to_thread(call_llm, _SYSTEM, user_msg)

        # 手機上先看 5 行結論，完整報告在 PDF
        brief = _extract_brief(content)
        if brief:
            await query.message.reply_text(
                f"{ticker} — {label}\n\n{brief}\n\n"
                "ℹ️ 這是分析框架示範，重點在拆解方法與數據依據，不是投資建議。"
            )

        pdf_bytes = generate_pdf(ticker, label, content)

        today = date.today().strftime("%Y%m%d")
        company_name = stock_data.get("name", "") if isinstance(stock_data, dict) else ""
        if is_taiwan_stock(ticker) and company_name:
            filename = f"{ticker}_{company_name}_{today}.pdf"
        else:
            filename = f"{ticker}_{today}.pdf"

        await query.message.reply_document(
            document=pdf_bytes,
            filename=filename,
            caption=f"✅ {ticker} — {label}｜分析框架示範，非投資建議",
        )
        await query.edit_message_text(f"✅ {ticker} {label} 分析完成")

    except Exception as exc:
        logger.error("Analysis failed for %s/%s: %s", ticker, analysis_key, exc, exc_info=True)
        await query.edit_message_text("❌ 分析失敗，請稍後再試")


@register("analyze")
async def _pending_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await analyze_command(update, context)


def build_analyze_handler(auth_filter):
    return [
        CommandHandler("analyze", analyze_command, filters=auth_filter),
        CallbackQueryHandler(analyze_pick_callback, pattern="^apick_"),
        CallbackQueryHandler(analyze_callback, pattern="^analyze_"),
    ]
