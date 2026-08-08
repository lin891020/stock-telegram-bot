"""證據包：集中管理本次真的抓到什麼，並算出「這次少了什麼」。

防幻覺的關鍵不是叫模型自律，而是把主導權從模型手上拿走：

1. prompt 裡只出現真的查到的數字，每筆標來源
2. 缺漏清單由**程式**算出來——模型無權決定要不要承認自己沒資料
3. 沒資料的章節明確要求略過，而不是逼它填滿（逼它填 = 逼它編）

有些需求是**已知永遠拿不到**的（同業估值對照、護城河量化評分）。
這些用空的來源清單表示，會固定出現在缺漏區。這是誠實，不是失敗。
"""
from dataclasses import dataclass, field

# 需求描述 → 能滿足它的 fact key；空 tuple = 目前沒有任何資料源，必定缺漏
_Requirement = tuple[str, tuple[str, ...]]

# 合成 key（非 yfinance 欄位），代表某一整塊資料是否到手
NAME = "company_name"
QUOTE = "quote"
RELEASE = "earnings_release"   # 公司自己寫的財報新聞稿原文（SEC EDGAR）
EPS_ACTUAL = "eps_actual"      # 本季實際 EPS
EPS_ESTIMATE = "eps_estimate"  # 市場預估 EPS，beat/miss 的另一半
FIN_ANNUAL = "financials_annual"
FIN_QUARTERLY = "financials_quarterly"

_COMMON: list[_Requirement] = [
    ("標的公司名稱", (NAME,)),
    ("即時股價", (QUOTE,)),
    ("年度財務報表", (FIN_ANNUAL,)),
]

REQUIREMENTS: dict[str, list[_Requirement]] = {
    "full": _COMMON + [
        ("季度財務報表", (FIN_QUARTERLY,)),
        ("獲利能力指標（毛利率、營益率、淨利率）", ("grossMargins", "operatingMargins", "profitMargins")),
        ("股東權益報酬率（ROE）", ("returnOnEquity",)),
        ("估值指標（本益比、P/S、P/B）", ("trailingPE", "priceToBook")),
        ("分析師目標價與共識評級", ("targetMeanPrice", "recommendationKey")),
        ("同業估值對照數據", ()),
        ("產業市場規模與成長率預估", ()),
    ],
    "financial": _COMMON + [
        ("季度財務報表", (FIN_QUARTERLY,)),
        ("獲利能力指標（毛利率、營益率、淨利率）", ("grossMargins", "operatingMargins", "profitMargins")),
        ("股東權益報酬率（ROE）", ("returnOnEquity",)),
        ("完整負債結構（totalDebt 僅含借款，非總負債）", (FIN_ANNUAL,)),
        ("現金與借款部位", ("totalCash", "totalDebt")),
        ("自由現金流", ("freeCashflow",)),
        ("同業財務體質對照數據", ()),
    ],
    "moat": _COMMON + [
        ("獲利能力指標（毛利率長期高低是護城河的間接證據）", ("grossMargins", "operatingMargins")),
        ("品牌價值、轉換成本、網路效應的量化數據", ()),
        ("專利數量與訴訟紀錄", ()),
        ("市占率數據", ()),
    ],
    "valuation": _COMMON + [
        ("估值指標（本益比、預估本益比、P/S、P/B）", ("trailingPE", "forwardPE")),
        ("分析師目標價區間與涵蓋人數", ("targetMeanPrice", "numberOfAnalystOpinions")),
        ("同業估值對照數據", ()),
        ("DCF 所需的長期現金流預測", ()),
    ],
    "growth": _COMMON + [
        ("營收與獲利成長率（年增）", ("revenueGrowth", "earningsGrowth")),
        ("季度財務報表", (FIN_QUARTERLY,)),
        ("產業市場規模與成長率預估", ()),
        ("公司官方財測（guidance）", ()),
    ],
    "debate": _COMMON + [
        ("估值指標", ("trailingPE",)),
        ("成長率", ("revenueGrowth",)),
        ("分析師共識評級", ("recommendationKey",)),
        ("同業對照數據", ()),
    ],
    # 財報公布後的事實摘要：決策用，標準比 /analyze 嚴格。
    # 這裡不要求同業與產業資料——那些拿不到，列進來只會每季重複洗版。
    "earnings": [
        ("標的公司名稱", (NAME,)),
        ("最新股價", (QUOTE,)),
        ("公司財報新聞稿原文（含管理層說法與官方財測）", (RELEASE,)),
        ("本季實際 EPS", (EPS_ACTUAL,)),
        ("市場預估 EPS（beat/miss 需要它）", (EPS_ESTIMATE,)),
        ("季度財務報表", (FIN_QUARTERLY,)),
    ],
    "recommendation": _COMMON + [
        ("估值指標", ("trailingPE", "forwardPE")),
        ("分析師目標價與共識評級", ("targetMeanPrice", "recommendationKey")),
        ("成長率", ("revenueGrowth",)),
        ("同業對照數據", ()),
        ("未來催化事件時程", ()),
    ],
}

# 本質上就是主觀判斷的分析類型：不假裝客觀，但也不假裝有數據
SUBJECTIVE_NOTES: dict[str, str] = {
    "moat": "護城河強弱沒有公開的量化資料源。本報告的護城河判斷屬模型推論，不得呈現為量化評分。",
    "debate": "多空論點本質是推論。每個論點必須標明它依據的是上方哪一項事實，或明確標示為推論。",
}


@dataclass
class Evidence:
    """本次分析可用的事實，以及程式判定的缺漏。"""

    ticker: str
    facts: dict[str, dict] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def has(self, key: str) -> bool:
        return key in self.facts

    def to_prompt(self) -> str:
        lines = [f"=== {self.ticker} 本次查到的事實（每筆標註來源）==="]

        grouped: dict[str, list[str]] = {}
        for fact in self.facts.values():
            period = fact.get("period") or ""
            head = f"- {fact['label']}"
            if period:
                head += f"（{period}）"
            head += f"：{fact['display']}　[來源：{fact['source']}]"
            if fact.get("definition"):
                head += f"\n    ※ {fact['definition']}"
            grouped.setdefault(fact.get("group", "其他"), []).append(head)
        for group, items in grouped.items():
            lines.append("")
            lines.append(f"【{group}】")
            lines.extend(items)

        lines.append("")
        lines.append(
            "期間規則：括號內是該數字涵蓋的期間。不同期間的數字不得直接相比，"
            "也不得把某期間的比率安到另一期間的絕對值上"
            "（例如把單季年增率說成年度成長率）。引用時必須連期間一起寫出來。"
        )

        lines.append("")
        lines.append("=== 本次無法取得的資料 ===")
        if self.missing:
            lines.extend(f"- {m}" for m in self.missing)
            lines.append("")
            lines.append(
                "以上項目一律不得推測、估算，或引用你訓練資料中的數字填補。"
                "需要用到這些資料的段落請整段略過，並在報告的缺漏區重述。"
            )
        else:
            lines.append("（無，本次所需資料齊全）")

        if self.notes:
            lines.append("")
            lines.append("=== 額外說明 ===")
            lines.extend(f"- {n}" for n in self.notes)

        return "\n".join(lines)

    def missing_block(self) -> str:
        """給報告結尾用的缺漏區文字。"""
        if not self.missing:
            return ""
        return "本次無法取得的資料（以下項目未納入分析）：\n" + "\n".join(
            f"- {m}" for m in self.missing
        )


def _quote_display(stock_data: dict) -> str:
    price = stock_data.get("price") or stock_data.get("close")
    prev = stock_data.get("prev_close")
    text = f"{price:,.2f}" if price else "無報價"
    if price and prev:
        pct = (price - prev) / prev * 100
        text += f"（前收 {prev:,.2f}，{pct:+.2f}%）"
    return text


def build_evidence(
    ticker: str,
    analysis_key: str,
    stock_data: dict | None,
    financials: dict | None,
    metrics: dict[str, dict] | None,
    anomalies: list[str] | None = None,
) -> Evidence:
    """組裝證據包並算出缺漏。缺漏是程式判定的，不經過模型。"""
    ev = Evidence(ticker=ticker)
    for anomaly in anomalies or []:
        ev.notes.append(f"資料源異常，已剔除相關指標：{anomaly}")

    stock_data = stock_data if isinstance(stock_data, dict) else {}
    financials = financials if isinstance(financials, dict) else {}
    metrics = metrics or {}

    # 公司名稱必須是事實。少了它，模型只拿到「2408」四個數字，
    # 只能從記憶猜公司——實測它把南亞科(2408)猜成聯電(2303)，整份報告寫錯公司。
    name = stock_data.get("name") or ""
    if name and name != ticker:
        ev.facts[NAME] = {
            "label": "公司名稱",
            "display": name,
            "source": "TWSE" if stock_data.get("market") == "TW" else "yfinance",
            "period": "",
            "group": "標的識別",
        }
    else:
        ev.missing.append(
            f"代號 {ticker} 對應的公司名稱（不得自行推測是哪一家公司，"
            "若無法確認標的身分，請直接說明無法分析）"
        )

    if stock_data and not stock_data.get("error"):
        ev.facts[QUOTE] = {
            "label": "最新股價",
            "display": _quote_display(stock_data),
            "source": "TWSE" if stock_data.get("market") == "TW" else "yfinance",
            "period": str(stock_data.get("date") or "最新交易日"),
            "group": "即時報價",
        }
    fin_error = financials.get("error")
    if fin_error:
        ev.notes.append(f"財務報表抓取失敗：{fin_error}")
    else:
        annual = financials.get("annual") or {}
        quarterly = financials.get("quarterly") or {}
        is_tw = financials.get("market") == "TW"
        source = "FinMind" if is_tw else "yfinance"
        # 兩條路徑的年度數字來源不同，註記不能共用一句
        annual_note = (
            "損益與現金流為該年度各季加總；資產負債為該年度最新一期"
            if is_tw else
            "資料源直接提供的年報數字，未經加總"
        )
        if any(annual.values()):
            ev.facts[FIN_ANNUAL] = {
                "label": "年度財報",
                "display": _format_financial_block(annual),
                "source": source,
                "period": "各年度，鍵名標明是否為完整年度",
                "definition": annual_note,
                "group": "財務報表",
            }
        if any(quarterly.values()):
            ev.facts[FIN_QUARTERLY] = {
                "label": "季度財報",
                "display": _format_quarterly_block(quarterly),
                "source": source,
                "period": "近 4 季，各季單季數、非累計",
                "group": "財務報表",
            }

    for key, metric in metrics.items():
        ev.facts[key] = {**metric, "group": "關鍵指標"}

    for description, satisfied_by in REQUIREMENTS.get(analysis_key, _COMMON):
        if not satisfied_by or not any(ev.has(k) for k in satisfied_by):
            ev.missing.append(description)

    note = SUBJECTIVE_NOTES.get(analysis_key)
    if note:
        ev.notes.append(note)

    return ev


def _fmt_num(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    for div, unit in ((1e12, "兆"), (1e8, "億"), (1e4, "萬")):
        if abs(n) >= div:
            return f"{n / div:,.2f}{unit}"
    return f"{n:,.0f}"


_ANNUAL_LABELS = [
    ("revenue", "營收"), ("cost_of_goods", "營業成本"), ("gross_profit", "毛利"),
    ("rnd", "研發費用"), ("sga", "管銷費用"), ("operating_expenses", "營業費用"),
    ("operating_income", "營業利益"), ("pretax_income", "稅前淨利"),
    ("tax", "所得稅"), ("net_income", "淨利"), ("eps", "每股盈餘"),
    ("total_assets", "總資產"), ("total_liabilities", "總負債"),
    ("equity", "股東權益"), ("operating_cashflow", "營業現金流"), ("capex", "資本支出"),
]


def _format_financial_block(annual: dict) -> str:
    parts = []
    for key, label in _ANNUAL_LABELS:
        series = annual.get(key) or {}
        if not series:
            continue
        body = "　".join(f"{year}: {_fmt_num(v)}" for year, v in sorted(series.items()))
        parts.append(f"\n    {label}：{body}")
    return "".join(parts) if parts else "無資料"


def _format_quarterly_block(quarterly: dict) -> str:
    parts = []
    for key, label in (
        ("revenue", "營收"), ("pretax_income", "稅前淨利"),
        ("tax", "所得稅"), ("net_income", "淨利"),
    ):
        rows = quarterly.get(key) or []
        if not rows:
            continue
        body = "　".join(f"{r.get('date', '')}: {_fmt_num(r.get('value'))}" for r in rows)
        parts.append(f"\n    {label}：{body}")
    return "".join(parts) if parts else "無資料"
