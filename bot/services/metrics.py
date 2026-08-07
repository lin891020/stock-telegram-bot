"""估值、獲利能力、分析師預期等關鍵指標。

這些數字 yfinance 本來就給，但以前完全沒餵進 prompt，
導致模型只能憑訓練記憶「編」出本益比、目標價、利潤率。

每個欄位在 METRIC_SPECS 註冊三件事，缺一不可：

- period：這個數字算的是**哪段期間**。少了它就會發生「拿單季年增率
  16.40% 安在年度營收上」（實測 AAPL，年度實際只成長 6.43%）。
- definition：這個數字**到底是什麼**。少了它就會發生「把只含借款的
  totalDebt 當成總負債」（實測 AAPL，843 億 vs 實際 2,855 億）。
- label：顯示名稱一律從註冊表生成，不在別處手打，避免標籤與語義脫鉤。
"""
import asyncio
import logging
from dataclasses import dataclass

import yfinance as yf

from bot.services.stock import is_taiwan_stock

logger = logging.getLogger(__name__)

SOURCE = "yfinance"

_TTM = "TTM／近 12 個月"
_LATEST_BS = "最新一期資產負債表"
_QUARTER_YOY = "最近一季 YoY"
_ANALYST = "分析師預估／未來 12 個月"
_STATIC = ""


@dataclass(frozen=True)
class MetricSpec:
    label: str
    kind: str  # pct / num / int / money / text
    period: str
    definition: str = ""


METRIC_SPECS: dict[str, MetricSpec] = {
    "trailingPE": MetricSpec("本益比", "num", _TTM),
    "forwardPE": MetricSpec(
        "預估本益比", "num", _ANALYST,
        "分母是分析師預估 EPS，不是已實現獲利；預估落空則此數字失效",
    ),
    "priceToSalesTrailing12Months": MetricSpec("股價營收比（P/S）", "num", _TTM),
    "priceToBook": MetricSpec("股價淨值比（P/B）", "num", _LATEST_BS),
    "grossMargins": MetricSpec("毛利率", "pct", _TTM),
    "operatingMargins": MetricSpec("營業利益率", "pct", _TTM),
    "profitMargins": MetricSpec("淨利率", "pct", _TTM),
    "returnOnEquity": MetricSpec(
        "股東權益報酬率（ROE）", "pct", _TTM,
        "淨利 ÷ 股東權益；大額庫藏股會壓縮權益而墊高此值，不等於經營效率提升",
    ),
    "revenueGrowth": MetricSpec(
        "營收年增率", "pct", _QUARTER_YOY,
        "這是「單季」對去年同季的成長率，不是年度成長率，不可安在年度營收上",
    ),
    "earningsGrowth": MetricSpec(
        "獲利年增率", "pct", _QUARTER_YOY,
        "這是「單季」對去年同季的成長率，不是年度成長率",
    ),
    "targetMeanPrice": MetricSpec("分析師目標價（平均）", "num", _ANALYST),
    "targetHighPrice": MetricSpec("分析師目標價（最高）", "num", _ANALYST),
    "targetLowPrice": MetricSpec("分析師目標價（最低）", "num", _ANALYST),
    "numberOfAnalystOpinions": MetricSpec("涵蓋分析師人數", "int", "當前"),
    "recommendationKey": MetricSpec("分析師共識評級", "text", "當前"),
    "freeCashflow": MetricSpec("自由現金流", "money", _TTM),
    "totalDebt": MetricSpec(
        "有息負債", "money", _LATEST_BS,
        "僅含計息借款，不含應付帳款等其他負債；與資產負債表的「總負債」是兩回事，"
        "不可用它計算淨現金部位或負債比",
    ),
    "totalCash": MetricSpec(
        "現金部位", "money", _LATEST_BS,
        "含約當現金與短期投資，大於資產負債表的「現金及約當現金」",
    ),
    "sector": MetricSpec("產業（大類）", "text", _STATIC),
    "industry": MetricSpec("產業（細類）", "text", _STATIC),
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


# 會計恆等關係：毛利率 ≥ 營業利益率 ≥ 淨利率（同期間）
_MARGIN_CHAIN = ["grossMargins", "operatingMargins", "profitMargins"]


def check_margin_consistency(info: dict) -> list[str]:
    """檢查利潤率是否自相矛盾。

    毛利率一定 ≥ 營益率 ≥ 淨利率，這是定義決定的。違反就代表資料源
    的期間口徑不一致（實測 2408：營益率 73.68% > 毛利率 64.91%）。
    這種矛盾要由程式擋，不能指望模型看出來——它會照抄。
    """
    chain = []
    for key in _MARGIN_CHAIN:
        value = info.get(key)
        if isinstance(value, (int, float)):
            chain.append((METRIC_SPECS[key].label, float(value)))

    problems = []
    for (upper_label, upper), (lower_label, lower) in zip(chain, chain[1:]):
        if lower > upper:
            problems.append(
                f"{lower_label}（{lower * 100:.2f}%）高於 {upper_label}（{upper * 100:.2f}%），"
                "違反會計恆等關係，代表資料源期間口徑不一致，本次全部利潤率均不採用"
            )
    return problems


def extract_metrics(info: dict) -> tuple[dict[str, dict], list[str]]:
    """挑出關鍵指標並做一致性檢查。

    回傳 (指標, 異常說明)。缺的欄位不放進來（不填 N/A、不補預設值）；
    自相矛盾的利潤率整組剔除——分不出哪個錯時，一個都不能用。
    """
    anomalies = check_margin_consistency(info)
    dropped = set(_MARGIN_CHAIN) if anomalies else set()

    metrics = {}
    for key, spec in METRIC_SPECS.items():
        value = info.get(key)
        if value is None or value == "" or value == {} or key in dropped:
            continue
        metrics[key] = {
            "label": spec.label,
            "value": value,
            "display": format_metric(value, spec.kind),
            "period": spec.period,
            "definition": spec.definition,
            "source": SOURCE,
        }
    return metrics, anomalies


async def fetch_key_metrics(ticker: str) -> tuple[dict[str, dict], list[str]]:
    info = await asyncio.to_thread(_fetch_info_sync, ticker)
    return extract_metrics(info)
