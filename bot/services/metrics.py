"""估值、獲利能力、分析師預期等關鍵指標。

這些數字 yfinance 本來就給，但以前完全沒餵進 prompt，
導致模型只能憑訓練記憶「編」出本益比、目標價、利潤率——
而且編得很像真的。抓得到就餵真的，抓不到就讓它進缺漏清單。

每個指標都帶來源標記，不補值、不估算、不沿用上次的結果。
"""
import asyncio
import logging

import yfinance as yf

from bot.services.stock import is_taiwan_stock

logger = logging.getLogger(__name__)

SOURCE = "yfinance"

# yfinance 欄位 → (顯示名稱, 格式類型)
# pct = 小數轉百分比、num = 兩位小數、int = 整數、money = 億/兆縮寫、text = 原文
METRIC_SPECS: dict[str, tuple[str, str]] = {
    "trailingPE": ("本益比（TTM）", "num"),
    "forwardPE": ("預估本益比（Forward）", "num"),
    "priceToSalesTrailing12Months": ("股價營收比（P/S）", "num"),
    "priceToBook": ("股價淨值比（P/B）", "num"),
    "grossMargins": ("毛利率", "pct"),
    "operatingMargins": ("營業利益率", "pct"),
    "profitMargins": ("淨利率", "pct"),
    "returnOnEquity": ("股東權益報酬率（ROE）", "pct"),
    "revenueGrowth": ("營收成長率（年增）", "pct"),
    "earningsGrowth": ("獲利成長率（年增）", "pct"),
    "targetMeanPrice": ("分析師目標價（平均）", "num"),
    "targetHighPrice": ("分析師目標價（最高）", "num"),
    "targetLowPrice": ("分析師目標價（最低）", "num"),
    "numberOfAnalystOpinions": ("涵蓋分析師人數", "int"),
    "recommendationKey": ("分析師共識評級", "text"),
    "freeCashflow": ("自由現金流", "money"),
    "totalDebt": ("總負債", "money"),
    "totalCash": ("現金及約當現金", "money"),
    "sector": ("產業（大類）", "text"),
    "industry": ("產業（細類）", "text"),
}


def format_metric(value, kind: str) -> str:
    """把原始值轉成人看得懂的字串。無法轉換就回原值的字串形式。"""
    try:
        if kind == "pct":
            return f"{float(value) * 100:.2f}%"
        if kind == "num":
            return f"{float(value):,.2f}"
        if kind == "int":
            return f"{int(value):,}"
        if kind == "money":
            n = float(value)
            for div, unit in ((1e12, "兆"), (1e8, "億"), (1e4, "萬")):
                if abs(n) >= div:
                    return f"{n / div:,.2f}{unit}"
            return f"{n:,.0f}"
    except (TypeError, ValueError):
        pass
    return str(value)


def _fetch_info_sync(ticker: str) -> dict:
    """台股先試上市（.TW）再試上櫃（.TWO），與 earnings 服務的探測方式一致。"""
    candidates = [f"{ticker}.TW", f"{ticker}.TWO"] if is_taiwan_stock(ticker) else [ticker]
    for symbol in candidates:
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as e:
            logger.warning("metrics info failed for %s: %s", symbol, e)
            continue
        if info.get("longName") or info.get("currentPrice") or info.get("regularMarketPrice"):
            return info
    return {}


def extract_metrics(info: dict) -> dict[str, dict]:
    """從 info 挑出關鍵指標。缺的欄位直接不放進來（不填 N/A、不補預設值）。"""
    metrics = {}
    for key, (label, kind) in METRIC_SPECS.items():
        value = info.get(key)
        if value is None or value == "" or value == {}:
            continue
        metrics[key] = {
            "label": label,
            "value": value,
            "display": format_metric(value, kind),
            "source": SOURCE,
        }
    return metrics


async def fetch_key_metrics(ticker: str) -> dict[str, dict]:
    info = await asyncio.to_thread(_fetch_info_sync, ticker)
    return extract_metrics(info)
