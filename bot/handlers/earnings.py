import asyncio
import logging
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.config import ALLOWED_TELEGRAM_ID
from bot.handlers.messaging import failure_text, send_long
from bot.handlers.pending import ask, register
from bot.services.earnings import fetch_earnings_data
from bot.services.earnings_watch import (
    all_watchlist_tickers, commit_event, detect_earnings_event, prune_state,
)
from bot.services.earnings_report import build_brief, build_full_report
from bot.services.formatting import safe_filename
from bot.services.pdf import generate_pdf
from bot.services.stock import looks_like_ticker, search_ticker, is_taiwan_stock
from bot.services.tw_stocks import search_tw_stocks, has_chinese

logger = logging.getLogger(__name__)

def _report_button(ticker: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 完整報告", callback_data=f"erpt_{ticker}")
    ]])


# 速覽裡最多列這麼多項缺漏，其餘收合。全部列出來會蓋過本季數字本身。
_MAX_MISSING_SHOWN = 4


def _missing_block(missing: list[str]) -> str:
    """把缺漏「列出來」而不是只報數量。

    整套設計的原則是「寧可說查不到，不可用舊資料假裝現況」，但速覽
    以前只寫「⚠️ 本次缺漏 3 項」——說了數量卻沒說是什麼，讀的人
    無從判斷缺的那幾項會不會動搖結論。
    """
    if not missing:
        return ""
    shown = missing[:_MAX_MISSING_SHOWN]
    lines = "\n".join(f"　• {m}" for m in shown)
    rest = len(missing) - len(shown)
    tail = f"\n　• 還有 {rest} 項（完整報告內有清單）" if rest > 0 else ""
    return f"\n\n⚠️ 本次查不到（{len(missing)} 項）：\n{lines}{tail}"


def _format_quarter_history(quarters: list[dict], ticker: str = "") -> str:
    """近幾季 EPS 的 beat/miss，純程式計算、不經模型。

    這裡標的是**公布日**而不是財季代號。以前用「公布月份 → 曆年季別」
    推算，對非曆年制的公司整片標錯——NVDA 五月公布的其實是 FY2027 Q1，
    卻被標成 Q12026。財年結束月各家不同，光看公布日推不出來，
    與其標一個看起來像真的的錯代號，不如誠實寫公布日。
    """
    rows = [q for q in quarters if q.get("date")]
    if not rows:
        return ""
    currency = "NT$" if is_taiwan_stock(ticker) else "$"

    lines = []
    for q in sorted(rows, key=lambda r: r["date"], reverse=True)[:4]:
        eps_act, eps_est = q.get("eps_actual"), q.get("eps_estimate")
        if eps_act is not None:
            part = f"EPS {currency}{eps_act:.2f}"
            if eps_est is not None:
                diff = eps_act - eps_est
                arrow = "▲ beat" if diff >= 0 else "▼ miss"
                pct = (diff / abs(eps_est) * 100) if eps_est else 0
                part += f"（預估 {currency}{eps_est:.2f}，{arrow} {pct:+.1f}%）"
        elif eps_est is not None:
            part = f"EPS 預估 {currency}{eps_est:.2f}（尚未公布）"
        else:
            continue
        lines.append(f"• {q['date']} 公布：{part}")

    return "近幾季 EPS（依公布日）\n" + "\n".join(lines) if lines else ""


async def _run_earnings_analysis(ticker: str) -> tuple[str, str]:
    """財報速覽 + 近幾季 EPS 紀錄。回傳 (文字, label)。

    走的是跟自動推播同一條證據包路徑：每個數字都標來源與期間，
    缺的就明講缺。舊版在這裡自己出一個「財報品質 1-10 分」，
    那個分數沒有任何資料支撐，純粹是模型編的。
    """
    brief, evidence, label = await build_brief(ticker)

    parts = [f"📋 {label} 財報速覽", "", brief]

    data = await fetch_earnings_data(ticker)
    if not data.get("error"):
        history = _format_quarter_history(data.get("quarters", []), ticker)
        if history:
            parts += ["", history]
        next_date = data.get("next_earnings_date")
        if next_date:
            parts += ["", f"下次財報日：{next_date}"]

    missing = _missing_block(evidence.missing)
    if missing:
        parts.append(missing)

    return "\n".join(parts), label


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

    status = await update.message.reply_text(
        f"⏳ 正在查詢 {ticker} 財報...\n抓 SEC 原文＋財務數據，約 20-30 秒"
    )
    try:
        result, _ = await _run_earnings_analysis(ticker)
        await status.delete()
        await send_long(
            context.bot, update.message.chat_id, result,
            reply_markup=_report_button(ticker),
        )
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
    except Exception as e:
        logger.error("earnings failed for %s: %s", ticker, e, exc_info=True)
        await update.message.reply_text(failure_text(e))


@restrict_callback
async def earnings_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ticker = query.data.replace("epick_", "", 1)
    await query.edit_message_text(
        f"⏳ 正在查詢 {ticker} 財報...\n抓 SEC 原文＋財務數據，約 20-30 秒"
    )
    try:
        result, _ = await _run_earnings_analysis(ticker)
        await send_long(
            context.bot, query.message.chat_id, result,
            reply_markup=_report_button(ticker),
        )
    except ValueError as e:
        await query.edit_message_text(f"❌ {e}")
    except Exception as e:
        logger.error("earnings failed for %s: %s", ticker, e, exc_info=True)
        await query.edit_message_text(failure_text(e))


@register("earnings")
async def _pending_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    context.args = update.message.text.split()
    await earnings_command(update, context)


async def poll_earnings_announcements(context: ContextTypes.DEFAULT_TYPE) -> None:
    """定時執行：掃所有自選股，偵測到財報公布就推一則速覽。

    觸發以 SEC 官方申報為主、yfinance 的 EPS 為輔（見 earnings_watch）。
    完整報告不自動生成——財報季擠在兩三週內，每份都跑主力模型太貴，
    而且多數時候你看完速覽就夠了。想看深的再按按鈕。
    """
    try:
        tickers = all_watchlist_tickers()
        if not tickers:
            return
        prune_state(tickers)

        for ticker in tickers:
            try:
                event = await detect_earnings_event(ticker)
                if not event:
                    continue

                brief, evidence, label = await build_brief(ticker)
                missing_note = _missing_block(evidence.missing)
                await send_long(
                    context.bot,
                    ALLOWED_TELEGRAM_ID,
                    f"📋 {label} 財報公布（{event['date']}・{event['signal']}）\n\n"
                    f"{brief}{missing_note}",
                    reply_markup=_report_button(ticker),
                )
                # 推播成功才推進基準。順序反過來的話，build_brief 一出錯
                # （LLM 逾時、SEC 限流）那一季就永遠不會再被推播了。
                commit_event(ticker, event["date"])
                logger.info("earnings brief pushed for %s (%s)", ticker, event["signal"])
            except Exception as e:
                logger.error("earnings push failed for %s: %s", ticker, e, exc_info=True)
    except Exception as e:
        logger.error("poll_earnings_announcements failed: %s", e, exc_info=True)


@restrict_callback
async def earnings_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """速覽的 📄 按鈕：現生完整報告並出 PDF。"""
    query = update.callback_query
    await query.answer()

    ticker = query.data[len("erpt_"):]
    status = await query.message.reply_text(
        f"⏳ 正在整理 {ticker} 完整財報解讀...\n六個章節＋PDF 排版，約 40-60 秒"
    )
    try:
        content, label = await build_full_report(ticker)
        pdf_bytes = generate_pdf(label, "財報解讀", content)
        await query.message.reply_document(
            document=pdf_bytes,
            filename=f"{safe_filename(label)}_財報_{date.today().strftime('%Y%m%d')}.pdf",
            caption=f"✅ {label} 財報解讀",
        )
        await status.delete()
    except Exception as e:
        logger.error("earnings report failed for %s: %s", ticker, e, exc_info=True)
        await status.edit_text(failure_text(e, "報告生成失敗"))


def build_earnings_handler(auth_filter):
    return [
        CommandHandler("earnings", earnings_command, filters=auth_filter),
        CallbackQueryHandler(earnings_pick_callback, pattern="^epick_"),
        CallbackQueryHandler(earnings_report_callback, pattern="^erpt_"),
    ]
