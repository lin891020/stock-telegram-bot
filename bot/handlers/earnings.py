import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.services.earnings import fetch_earnings_data
from bot.services.llm import call_llm
from bot.services.stock import looks_like_ticker, search_ticker

logger = logging.getLogger(__name__)


def _build_quarters_block(quarters: list[dict]) -> str:
    if not quarters:
        return "（無歷史財報資料）"
    lines = []
    for q in quarters:
        dt = q.get("date", "")
        year = dt[:4]
        month = int(dt[5:7]) if len(dt) >= 7 else 0
        quarter_map = {1: "Q1", 2: "Q1", 3: "Q1",
                       4: "Q2", 5: "Q2", 6: "Q2",
                       7: "Q3", 8: "Q3", 9: "Q3",
                       10: "Q4", 11: "Q4", 12: "Q4"}
        q_label = f"{quarter_map.get(month, '?')}{year}" if year else dt

        eps_est = q.get("eps_estimate")
        eps_act = q.get("eps_actual")
        surprise = q.get("eps_surprise_pct")
        revenue = q.get("revenue")

        eps_part = ""
        if eps_act is not None:
            eps_part = f"EPS ${eps_act:.2f}"
            if eps_est is not None:
                beat = eps_act - eps_est
                arrow = "▲ beat" if beat >= 0 else "▼ miss"
                pct = (beat / abs(eps_est) * 100) if eps_est != 0 else 0
                sign = "+" if pct >= 0 else ""
                eps_part += f"（預估 ${eps_est:.2f}，{arrow} {sign}{pct:.1f}%）"
        elif eps_est is not None:
            eps_part = f"EPS 預估 ${eps_est:.2f}（未公佈）"

        rev_part = f"｜營收 ${revenue:.2f}B" if revenue is not None else ""
        lines.append(f"{q_label}：{eps_part}{rev_part}")

    return "\n".join(lines)


async def earnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "請輸入股票代號或公司名稱，例如：\n/earnings TSLA\n/earnings 2330\n/earnings 泓德能源"
        )
        return

    query = " ".join(context.args).strip()
    ticker = query.upper()

    if not looks_like_ticker(query):
        await update.message.reply_text(f"搜尋「{query}」中...")
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

    data = await fetch_earnings_data(ticker)

    if data.get("error"):
        await update.message.reply_text(f"❌ {data['error']}")
        return

    name = data.get("name", ticker)
    next_date = data.get("next_earnings_date") or "未公佈"
    quarters_block = _build_quarters_block(data.get("quarters", []))

    system = "你是一位華爾街資深財務分析師，專門解讀企業季報。用繁體中文，語氣簡潔專業。"
    user = f"""【{ticker} {name} 財報速覽】

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

    try:
        result = await asyncio.to_thread(call_llm, system, user)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error("earnings LLM failed for %s: %s", ticker, e, exc_info=True)
        await update.message.reply_text("❌ 分析失敗，請稍後再試")


async def earnings_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ticker = query.data.replace("epick_", "", 1)
    await query.edit_message_text(f"⏳ 正在查詢 {ticker} 財報資料...")

    data = await fetch_earnings_data(ticker)

    if data.get("error"):
        await query.edit_message_text(f"❌ {data['error']}")
        return

    name = data.get("name", ticker)
    next_date = data.get("next_earnings_date") or "未公佈"
    quarters_block = _build_quarters_block(data.get("quarters", []))

    system = "你是一位華爾街資深財務分析師，專門解讀企業季報。用繁體中文，語氣簡潔專業。"
    user = f"""【{ticker} {name} 財報速覽】

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

    try:
        result = await asyncio.to_thread(call_llm, system, user)
        await query.message.reply_text(result)
    except Exception as e:
        logger.error("earnings LLM failed for %s: %s", ticker, e, exc_info=True)
        await query.edit_message_text("❌ 分析失敗，請稍後再試")


def build_earnings_handler(auth_filter):
    return [
        CommandHandler("earnings", earnings_command, filters=auth_filter),
        CallbackQueryHandler(earnings_pick_callback, pattern="^epick_"),
    ]
