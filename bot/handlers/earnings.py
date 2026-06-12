import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.config import ALLOWED_TELEGRAM_ID
from bot.handlers.messaging import reply_long, send_long
from bot.handlers.pending import ask, register
from bot.services.earnings import fetch_earnings_data
from bot.services.earnings_watch import get_pending_announcements, mark_analyzed
from bot.services.llm import call_llm
from bot.services.stock import looks_like_ticker, search_ticker, is_taiwan_stock
from bot.services.tw_stocks import search_tw_stocks, has_chinese

logger = logging.getLogger(__name__)

_LLM_SYSTEM = "你是一位華爾街資深財務分析師，專門解讀企業季報。用繁體中文，語氣簡潔專業。"
_LLM_PROMPT = """【{ticker} {name} 財報速覽】

下次財報日：{next_date}

最近 4 季表現：
{quarters_block}

請分析：
1. EPS beat/miss 趨勢（近 4 季整體表現）
2. 營收成長動能（是否穩健成長）
3. 整體財報品質評分（1-10 分）與關鍵風險
4. 給長期投資人的一句話建議

輸出格式規則（必須遵守）：
- 純文字，不要使用 # ## ### 標題符號
- 不要使用 ** 粗體符號
- 用「▲ beat」「▼ miss」標示 EPS 表現
- 結尾附上下次財報日提醒"""


def _build_quarters_block(quarters: list[dict], ticker: str = "") -> str:
    if not quarters:
        return "（無歷史財報資料）"
    currency = "NT$" if is_taiwan_stock(ticker) else "$"
    lines = []
    for q in quarters:
        dt = q.get("date", "")
        year = int(dt[:4]) if len(dt) >= 4 else 0
        month = int(dt[5:7]) if len(dt) >= 7 else 0

        # Earnings are announced ~1 month after the quarter ends.
        # Map announcement month → reported fiscal quarter.
        if month in (1, 2, 3):
            q_label = f"Q4{year - 1}" if year else dt
        elif month in (4, 5, 6):
            q_label = f"Q1{year}" if year else dt
        elif month in (7, 8, 9):
            q_label = f"Q2{year}" if year else dt
        elif month in (10, 11, 12):
            q_label = f"Q3{year}" if year else dt
        else:
            q_label = dt

        eps_est = q.get("eps_estimate")
        eps_act = q.get("eps_actual")
        revenue = q.get("revenue")

        eps_part = ""
        if eps_act is not None:
            eps_part = f"EPS {currency}{eps_act:.2f}"
            if eps_est is not None:
                beat = eps_act - eps_est
                arrow = "▲ beat" if beat >= 0 else "▼ miss"
                pct = (beat / abs(eps_est) * 100) if eps_est != 0 else 0
                sign = "+" if pct >= 0 else ""
                eps_part += f"（預估 {currency}{eps_est:.2f}，{arrow} {sign}{pct:.1f}%）"
        elif eps_est is not None:
            eps_part = f"EPS 預估 {currency}{eps_est:.2f}（未公佈）"

        rev_part = f"｜營收 {currency}{revenue:.2f}B" if revenue is not None else ""
        lines.append(f"{q_label}：{eps_part}{rev_part}")

    return "\n".join(lines)


async def _run_earnings_analysis(ticker: str) -> str:
    """Fetch earnings data and return LLM analysis text, or raise on error."""
    data = await fetch_earnings_data(ticker)
    if data.get("error"):
        raise ValueError(data["error"])

    name = data.get("name", ticker)
    next_date = data.get("next_earnings_date") or "未公佈"
    quarters_block = _build_quarters_block(data.get("quarters", []), ticker)

    user = _LLM_PROMPT.format(
        ticker=ticker, name=name, next_date=next_date, quarters_block=quarters_block
    )
    return await asyncio.to_thread(call_llm, _LLM_SYSTEM, user)


async def earnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await ask(update.message, context, "earnings", "輸入要查財報的股票代號或名稱：")
        return

    query = " ".join(context.args).strip()
    ticker = query.upper()

    if not looks_like_ticker(query):
        await update.message.reply_text(f"搜尋「{query}」中...")
        if has_chinese(query):
            results = search_tw_stocks(query)
        else:
            results = await asyncio.to_thread(search_ticker, query)
        if not results:
            await update.message.reply_text(
                f"找不到「{query}」相關的股票。\n請直接輸入股票代號，例如：/earnings 2330"
            )
            return
        keyboard = [
            [InlineKeyboardButton(
                f"{r['symbol']} — {r['name'][:30]}",
                callback_data=f"epick_{r['symbol']}",
            )]
            for r in results
        ]
        await update.message.reply_text(
            "找到以下結果，請選擇：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await update.message.reply_text(f"⏳ 正在查詢 {ticker} 財報資料...")
    try:
        result = await _run_earnings_analysis(ticker)
        await reply_long(update.message, result)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
    except Exception as e:
        logger.error("earnings failed for %s: %s", ticker, e, exc_info=True)
        await update.message.reply_text("❌ 分析失敗，請稍後再試")


@restrict_callback
async def earnings_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ticker = query.data.replace("epick_", "", 1)
    await query.edit_message_text(f"⏳ 正在查詢 {ticker} 財報資料...")
    try:
        result = await _run_earnings_analysis(ticker)
        await reply_long(query.message, result)
    except ValueError as e:
        await query.edit_message_text(f"❌ {e}")
    except Exception as e:
        logger.error("earnings failed for %s: %s", ticker, e, exc_info=True)
        await query.edit_message_text("❌ 分析失敗，請稍後再試")


@register("earnings")
async def _pending_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await earnings_command(update, context)


async def poll_earnings_announcements(context: ContextTypes.DEFAULT_TYPE) -> None:
    """每 30 分鐘執行：偵測財報公布（出現實際 EPS）後推送一次分析。"""
    try:
        pending = get_pending_announcements()
        if not pending:
            return

        for ticker, entry in pending.items():
            try:
                data = await fetch_earnings_data(ticker)
                if data.get("error"):
                    continue
                # ISO 日期字串可直接比大小：預期日（含）之後出現實際 EPS 即視為已公布
                announced = any(
                    q.get("eps_actual") is not None and q.get("date", "") >= entry["date"]
                    for q in data.get("quarters", [])
                )
                if not announced:
                    continue

                analysis = await _run_earnings_analysis(ticker)
                name = data.get("name", ticker)
                await send_long(
                    context.bot,
                    ALLOWED_TELEGRAM_ID,
                    f"📋 {name}({ticker}) 財報公布！\n\n{analysis}",
                )
                mark_analyzed(ticker)
            except Exception as e:
                logger.error("earnings announcement push failed for %s: %s", ticker, e, exc_info=True)
    except Exception as e:
        logger.error("poll_earnings_announcements failed: %s", e, exc_info=True)


def build_earnings_handler(auth_filter):
    return [
        CommandHandler("earnings", earnings_command, filters=auth_filter),
        CallbackQueryHandler(earnings_pick_callback, pattern="^epick_"),
    ]
