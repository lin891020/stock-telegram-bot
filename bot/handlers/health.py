"""/health：一鍵檢查各資料源是否正常，下次出現「查無」時能立刻分辨是誰的問題。"""
import asyncio
import logging

import httpx
import yfinance as yf
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from datetime import date, timedelta

from bot.services.alerts import get_alerts
from bot.services.filings import EARNINGS_FORMS, get_cik, list_filings
from bot.services.financials import _finmind_get
from bot.services.llm import call_llm, get_current_model, AVAILABLE_MODELS
from bot.services.watchlist import get_watchlist

logger = logging.getLogger(__name__)


def _check_yfinance() -> tuple[bool, str]:
    try:
        price = yf.Ticker("AAPL").fast_info.last_price
        return (True, f"AAPL ${price:.2f}") if price else (False, "回傳空值")
    except Exception as e:
        return False, type(e).__name__


def _check_twse() -> tuple[bool, str]:
    try:
        resp = httpx.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=10.0
        )
        resp.raise_for_status()
        return True, f"{len(resp.json())} 檔"
    except Exception as e:
        return False, type(e).__name__


def _check_sec() -> tuple[bool, str]:
    """財報偵測與管理層說法全靠 EDGAR，壞了整條財報線就啞掉。"""
    try:
        cik = get_cik("AAPL")
        if not cik:
            return False, "查不到 CIK（可能被限流或 User-Agent 被擋）"
        filings = list_filings(cik, EARNINGS_FORMS, limit=1)
        return (True, f"AAPL 最近申報 {filings[0]['date']}") if filings else (False, "無申報紀錄")
    except Exception as e:
        return False, type(e).__name__


def _check_finmind() -> tuple[bool, str]:
    try:
        rows = asyncio.run(_finmind_probe())
        return (True, f"2330 取得 {len(rows)} 筆") if rows else (False, "回傳空值（可能額度用盡）")
    except Exception as e:
        return False, type(e).__name__


async def _finmind_probe() -> list:
    start = (date.today() - timedelta(days=400)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient() as client:
        return await _finmind_get(client, "TaiwanStockFinancialStatements", "2330", start)


def _check_lxml() -> tuple[bool, str]:
    """yfinance 少了 lxml 會靜靜地拿不到任何財報日——實測無聲壞了兩個月。"""
    try:
        import lxml
        return True, f"lxml {lxml.__version__}"
    except ImportError:
        return False, "未安裝（財報日與財務表會全部抓不到）"


def _check_llm() -> tuple[bool, str]:
    try:
        call_llm("你只回覆 ok", "ping")
        return True, AVAILABLE_MODELS.get(get_current_model(), (get_current_model(),))[0]
    except Exception as e:
        return False, type(e).__name__


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ 檢查各資料源中...")
    yf_ok, tw_ok, sec_ok, fm_ok, lxml_ok, llm_ok = await asyncio.gather(
        asyncio.to_thread(_check_yfinance),
        asyncio.to_thread(_check_twse),
        asyncio.to_thread(_check_sec),
        asyncio.to_thread(_check_finmind),
        asyncio.to_thread(_check_lxml),
        asyncio.to_thread(_check_llm),
    )

    def line(ok_detail, name):
        ok, detail = ok_detail
        return f"{'✅' if ok else '❌'} {name}：{detail}"

    user_id = update.effective_user.id
    await update.message.reply_text(
        "🩺 系統健康檢查\n\n"
        f"{line(yf_ok, '美股/財報/新聞 (yfinance)')}\n"
        f"{line(tw_ok, '台股清單 (TWSE)')}\n"
        f"{line(sec_ok, '美股財報原文 (SEC EDGAR)')}\n"
        f"{line(fm_ok, '台股財報 (FinMind)')}\n"
        f"{line(lxml_ok, 'lxml 解析器')}\n"
        f"{line(llm_ok, 'AI 模型')}\n\n"
        f"目前模型：{AVAILABLE_MODELS.get(get_current_model(), (get_current_model(),))[0]}\n"
        f"追蹤股票：{len(get_watchlist(user_id))} 檔\n"
        f"價格提醒：{len(get_alerts(user_id))} 個"
    )


def build_health_handler(auth_filter):
    return CommandHandler("health", health_command, filters=auth_filter)
