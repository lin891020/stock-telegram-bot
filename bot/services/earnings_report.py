"""財報公布後的報告：速覽（推播）與完整版（按鈕出 PDF）。

跟 /analyze 的關鍵差別是原料。/analyze 只有結構化數字，要展開成長篇報告，
輸出資訊量大於輸入，那個缺口只能靠留白或編造來填。
這裡的原料是公司自己寫的財報新聞稿（動輒兩萬字元），做的是壓縮不是展開——
LLM 的主場，而且幾乎每一句都能溯源到原文。
"""
import asyncio
import logging

from bot.prompts.earnings_report import (
    BRIEF_SYSTEM, FULL_SYSTEM, brief_prompt, full_prompt,
)
from bot.services.earnings import fetch_earnings_data
from bot.services.evidence import EPS_ACTUAL, EPS_ESTIMATE, RELEASE, build_evidence
from bot.services.filings import fetch_earnings_release
from bot.services.formatting import name_label
from bot.services.financials import get_financials
from bot.services.llm import call_llm
from bot.services.metrics import fetch_key_metrics
from bot.services.stock import get_stock_summary, is_taiwan_stock

logger = logging.getLogger(__name__)

# 新聞稿最長餵這麼多字元。TSLA 的 41,677 字元裡後半多是財務報表附表，
# 管理層說法與財測都在前段，截斷不影響本報告要的東西。
_MAX_RELEASE_CHARS = 24000


def _latest_reported_quarter(earnings: dict) -> dict | None:
    quarters = [
        q for q in earnings.get("quarters", [])
        if q.get("eps_actual") is not None and q.get("date")
    ]
    return max(quarters, key=lambda q: q["date"]) if quarters else None


async def gather_earnings_evidence(ticker: str):
    """把本次財報要用的所有資料湊齊，回傳 (evidence, label, release)。"""
    stock_data, financials, metrics_result, earnings, release = await asyncio.gather(
        get_stock_summary(ticker),
        get_financials(ticker),
        fetch_key_metrics(ticker),
        fetch_earnings_data(ticker),
        asyncio.to_thread(fetch_earnings_release, ticker),
        return_exceptions=True,
    )

    def _ok(value, default):
        if isinstance(value, Exception):
            logger.warning("earnings evidence part failed for %s: %s", ticker, value)
            return default
        return value

    stock_data = _ok(stock_data, {})
    financials = _ok(financials, {})
    metrics, anomalies = _ok(metrics_result, ({}, []))
    earnings = _ok(earnings, {})
    release = _ok(release, None)

    name = (stock_data.get("name") or earnings.get("name") or "")
    label = name_label(ticker, name)

    evidence = build_evidence(ticker, "earnings", stock_data, financials, metrics, anomalies)

    quarter = _latest_reported_quarter(earnings)
    if quarter:
        evidence.facts[EPS_ACTUAL] = {
            "label": "本季實際 EPS",
            "display": f"{quarter['eps_actual']}",
            "period": f"財報日 {quarter['date']}",
            "definition": "",
            "source": "yfinance",
            "group": "本季財報",
        }
        if quarter.get("eps_estimate") is not None:
            surprise = quarter.get("eps_surprise_pct")
            text = f"{quarter['eps_estimate']}"
            if surprise is not None:
                text += f"（實際較預估 {surprise:+.2f}%）"
            evidence.facts[EPS_ESTIMATE] = {
                "label": "市場預估 EPS",
                "display": text,
                "period": f"財報日 {quarter['date']}",
                "definition": "分析師預估值，用來判斷 beat/miss；非公司財測",
                "source": "yfinance",
                "group": "本季財報",
            }

    if release:
        evidence.facts[RELEASE] = {
            "label": "公司財報新聞稿原文",
            "display": release["text"][:_MAX_RELEASE_CHARS],
            "period": f"申報日 {release['filed']}",
            "definition": (
                "公司送交 SEC 的正式文件。管理層說法與官方財測請直接引用此原文，"
                "不得改寫語氣；原文未提及的內容不得補充。"
                "⚠️ 原文的表格經 HTML 轉純文字後欄位對應會丟失，一長串數字未必"
                "對應鄰近的標題。除非某個數字與其名稱直接相鄰且無歧義，否則"
                "不要斷定它是季增還是年增、是本季還是累計——寧可只寫絕對金額，"
                "或直接說明無法從原文確認"
            ),
            "source": release["source"],
            "group": "公司原始文件",
        }
    elif not is_taiwan_stock(ticker):
        evidence.notes.append("SEC 未找到本次財報新聞稿，管理層說法與官方財測本次無法取得")
    else:
        evidence.notes.append(
            "台股未在 SEC 登記，無結構化的財報新聞稿來源；"
            "管理層說法請自行查閱公開資訊觀測站的法說會資料"
        )

    # 缺漏清單要在事實補齊後重算，否則 EPS 與新聞稿會被誤報為缺漏
    evidence.missing = _recompute_missing(evidence)
    return evidence, label, release


def _recompute_missing(evidence) -> list[str]:
    from bot.services.evidence import REQUIREMENTS
    missing = [m for m in evidence.missing if "公司名稱" in m]
    for description, satisfied_by in REQUIREMENTS["earnings"]:
        if not satisfied_by or not any(evidence.has(k) for k in satisfied_by):
            missing.append(description)
    return missing


async def build_brief(ticker: str) -> tuple[str, object, str]:
    """財報速覽（推播用）。回傳 (文字, evidence, label)。"""
    evidence, label, _ = await gather_earnings_evidence(ticker)
    user = f"{evidence.to_prompt()}\n\n{brief_prompt(label)}"
    # 這裡刻意不用輕量模型。晨報新聞摘要每天跑、內容也不精確敏感，
    # 用 Haiku 省成本合理；但財報速覽一年只跑約 36 次（9 支 × 4 季），
    # 每次都是決策用的，而實測輕量模型在密集財務表上會換錯單位、
    # 把季增讀成年增。省那點錢不划算。
    text = await asyncio.to_thread(call_llm, BRIEF_SYSTEM, user)
    return text.strip(), evidence, label


async def build_full_report(ticker: str) -> tuple[str, str]:
    """完整財報解讀（按鈕觸發，出 PDF）。回傳 (內容, label)。"""
    evidence, label, _ = await gather_earnings_evidence(ticker)
    user = f"{evidence.to_prompt()}\n\n{full_prompt(label)}"
    content = await asyncio.to_thread(call_llm, FULL_SYSTEM, user)
    return content, label
