"""/health：一鍵檢查各資料源是否正常，下次出現「查無」時能立刻分辨是誰的問題。"""
import asyncio
import logging

import httpx
import yfinance as yf
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from datetime import date, timedelta

from bot.config import ALLOWED_TELEGRAM_ID
from bot.services.alerts import get_alerts
from bot.services.filings import EARNINGS_FORMS, get_cik, list_filings
from bot.services.financials import FINMIND_TYPES, _finmind_get
from bot.services.llm import call_llm, get_current_model, AVAILABLE_MODELS, LLMUnavailable
from bot.services.pdf import font_status
from bot.services.watchlist import get_watchlist

logger = logging.getLogger(__name__)


def _model_label() -> str:
    info = AVAILABLE_MODELS.get(get_current_model())
    return info.label if info else get_current_model()


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
    """不只看「有沒有回東西」，還要看我們依賴的科目名稱在不在。

    只數筆數的話，FinMind 改一個科目名我們是查不出來的——它照樣回幾百筆，
    只有那一項默默變空。負債與權益就是這樣缺了很久沒人發現。
    """
    try:
        total, missing = asyncio.run(_finmind_probe())
    except Exception as e:
        return False, type(e).__name__
    if not total:
        return False, "回傳空值（可能額度用盡）"
    if missing:
        return False, f"缺少科目 {'、'.join(missing)}（FinMind 可能改名，該欄位會變空）"
    n = sum(len(v) for v in FINMIND_TYPES.values())
    return True, f"2330 取得 {total} 筆，{n} 個依賴科目齊全"


async def _finmind_probe() -> tuple[int, list[str]]:
    """回傳 (總筆數, 查無的科目名稱)。"""
    start = (date.today() - timedelta(days=400)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient() as client:
        datasets = list(FINMIND_TYPES)
        results = await asyncio.gather(
            *[_finmind_get(client, d, "2330", start) for d in datasets]
        )
    total, missing = 0, []
    for dataset, rows in zip(datasets, results):
        total += len(rows)
        seen = {r.get("type") for r in rows}
        missing += [t for t in FINMIND_TYPES[dataset] if t not in seen]
    return total, missing


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
        info = AVAILABLE_MODELS.get(get_current_model())
        return True, info.label if info else get_current_model()
    except LLMUnavailable as e:
        # 巡檢是半夜自己跑的，寫「RuntimeError」等於什麼都沒說
        return False, e.hint or e.reason
    except Exception as e:
        return False, type(e).__name__


# (顯示名稱, 檢查函式)。順序就是輸出順序。
_CHECKS = [
    ("美股/財報/新聞 (yfinance)", _check_yfinance),
    ("台股清單 (TWSE)", _check_twse),
    ("美股財報原文 (SEC EDGAR)", _check_sec),
    ("台股財報 (FinMind)", _check_finmind),
    ("lxml 解析器", _check_lxml),
    ("PDF 中文字型", font_status),
    ("AI 模型", _check_llm),
]


async def run_checks() -> list[tuple[str, bool, str]]:
    """跑完全部檢查，回傳 [(名稱, 是否正常, 細節)]。"""
    results = await asyncio.gather(
        *[asyncio.to_thread(fn) for _, fn in _CHECKS], return_exceptions=True
    )
    out = []
    for (name, _), result in zip(_CHECKS, results):
        if isinstance(result, Exception):
            out.append((name, False, type(result).__name__))
        else:
            ok, detail = result
            out.append((name, ok, detail))
    return out


def format_checks(results: list[tuple[str, bool, str]]) -> str:
    return "\n".join(f"{'✅' if ok else '❌'} {name}：{detail}" for name, ok, detail in results)


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = await update.message.reply_text("⏳ 檢查各資料源中...")
    results = await run_checks()
    user_id = update.effective_user.id
    failed = [name for name, ok, _ in results if not ok]
    verdict = "全部正常" if not failed else f"{len(failed)} 項異常"

    await status.edit_text(
        f"🩺 系統健康檢查｜{verdict}\n\n"
        f"{format_checks(results)}\n\n"
        f"目前模型：{_model_label()}\n"
        f"追蹤股票：{len(get_watchlist(user_id))} 檔\n"
        f"價格提醒：{len(get_alerts(user_id))} 個"
    )


async def health_watchdog(context: ContextTypes.DEFAULT_TYPE) -> None:
    """每天自動巡檢，只有壞掉才推播；全綠時保持安靜。

    /health 要「你想到去打」才會知道，但真正的問題是沒人會沒事去打它——
    lxml 缺套件那次靜靜壞了兩個月，就算當時有 /health 也一樣不會被發現。
    """
    try:
        results = await run_checks()
        failed = [(name, detail) for name, ok, detail in results if not ok]
        if not failed:
            logger.info("health watchdog: 七項全綠")
            return
        await context.bot.send_message(
            chat_id=ALLOWED_TELEGRAM_ID,
            text=(
                f"⚠️ 每日巡檢發現 {len(failed)} 項異常\n\n"
                + "\n".join(f"❌ {name}：{detail}" for name, detail in failed)
                + "\n\n受影響的功能可能會安靜地給出不完整的結果。"
            ),
        )
        logger.warning("health watchdog: %d 項異常 %s", len(failed), [n for n, _ in failed])
    except Exception as e:
        logger.error("health watchdog failed: %s", e, exc_info=True)


def build_health_handler(auth_filter):
    return CommandHandler("health", health_command, filters=auth_filter)
