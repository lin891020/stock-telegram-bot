"""/health：一鍵檢查各資料源是否正常，下次出現「查無」時能立刻分辨是誰的問題。"""
import asyncio
import logging

import httpx
import yfinance as yf
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.services.llm import call_llm, get_current_model, AVAILABLE_MODELS
from bot.services.watchlist import get_watchlist
from bot.services.alerts import get_alerts

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


def _check_llm() -> tuple[bool, str]:
    try:
        call_llm("你只回覆 ok", "ping")
        return True, AVAILABLE_MODELS.get(get_current_model(), (get_current_model(),))[0]
    except Exception as e:
        return False, type(e).__name__


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ 檢查各資料源中...")
    yf_ok, tw_ok, llm_ok = await asyncio.gather(
        asyncio.to_thread(_check_yfinance),
        asyncio.to_thread(_check_twse),
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
        f"{line(llm_ok, 'AI 模型')}\n\n"
        f"目前模型：{AVAILABLE_MODELS.get(get_current_model(), (get_current_model(),))[0]}\n"
        f"追蹤股票：{len(get_watchlist(user_id))} 檔\n"
        f"價格提醒：{len(get_alerts(user_id))} 個"
    )


def build_health_handler(auth_filter):
    return CommandHandler("health", health_command, filters=auth_filter)
