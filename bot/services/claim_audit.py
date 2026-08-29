"""報告產出後的數字稽核。證據包管「餵什麼進去」，consistency 管「餵的
東西對不對」，這裡管「模型寫出來的到底是不是那些數字」。

兩種做法，偵測力差很多：

  audit_numbers   問「這個數字推不推導得出來」。**實測幾乎沒有偵測力**
                  ——見下方 _derivations 的註解。留著只因為它對量級落在
                  推導空間縫隙裡的數字仍有效，而且不會誤報。

  verify_ratios   問「報告說毛利率 56.1%，那用本次資料算出來是多少」。
                  點對點比對，候選只有幾個期間，這才是有用的那一層。

FinGround 那篇論文的數據支持後者：計算類宣稱的幻覺率最高（28.4%），
而其中 43% 要靠重算才抓得到——重點在「重算」，不在「比對有沒有出現過」。
"""
import itertools
import logging
import re

logger = logging.getLogger(__name__)

# 相對誤差容忍度。報告會四捨五入（31.83% 寫成 31.8%），太嚴會全是誤報。
_TOLERANCE = 0.015

# 這些數字不值得追：個位數、年份、章節編號
_MIN_VALUE = 10.0
_YEAR_RANGE = (1990, 2100)

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> set[float]:
    """抓出文字裡有意義的數字。"""
    out = set()
    for m in _NUM_RE.finditer(text):
        try:
            value = float(m.group().replace(",", ""))
        except ValueError:
            continue
        if value < _MIN_VALUE or _YEAR_RANGE[0] <= value <= _YEAR_RANGE[1]:
            continue
        out.add(value)
    return out


def _close(a: float, b: float) -> bool:
    if b == 0:
        return abs(a) < _TOLERANCE
    return abs(a - b) / abs(b) <= _TOLERANCE


def _derivations(base: list[float]):
    """從證據包的數字能合法算出來的值。

    ⚠️ 這個做法實測幾乎沒有偵測力，不要以為有它就擋得住編造的數字。
    台積電的證據包有 46 個數字，兩兩排列產生 4,428 個推導值，把 0–100
    這段數線鋪滿了。把證據包裡的真數字擾動 5–50%（幻覺的典型樣貌）之後
    仍有 94% 被判為「算得出來」；一份 4,830 字元的真實報告有 36 個數字，
    它標記 0 個。候選集夠大時，「有沒有可能算出來」的答案永遠是「有」。

    真正有偵測力的是 verify_ratios（點對點重算）。這裡留著是因為它對
    落在推導空間縫隙裡的數字仍然有效，成本近乎零，而且不會誤報。
    """
    for x, y in itertools.permutations(base, 2):
        if y == 0:
            continue
        ratio = x / y
        if 0 < ratio < 100:
            yield ratio * 100        # 佔比／利潤率（%）
            yield (ratio - 1) * 100  # 成長率（%）
        yield x - y                  # 差額


def audit_numbers(report: str, evidence_text: str) -> list[float]:
    """回傳報告裡既不在證據包、也推導不出來的數字。"""
    ev_nums = extract_numbers(evidence_text)
    if not ev_nums:
        return []

    unexplained = []
    # 推導只用證據包裡較大的那些數字當基底，避免組合爆炸
    base = sorted(ev_nums, key=abs, reverse=True)[:40]
    derived = None

    for value in sorted(extract_numbers(report)):
        if any(_close(value, e) for e in ev_nums):
            continue
        if derived is None:
            derived = list(_derivations(base))
        if any(_close(value, d) for d in derived):
            continue
        unexplained.append(value)
    return unexplained


def audit_note(
    report: str,
    evidence_text: str,
    financials: dict | None = None,
    metrics: dict | None = None,
) -> str:
    """給報告附加的稽核結果；沒問題時回空字串。

    刻意不改寫報告——改寫要用模型驗模型，那是另一個量級的工程，而且會
    引入新的錯誤。這裡只做「說清楚哪幾個數字對不上」，跟整套設計
    「寧可說查不到」的原則一致。

    傳了 financials 才會做比率重算，而那是這個函式真正有偵測力的部分。
    """
    lines = []

    mismatched = verify_ratios(report, financials, metrics) if financials else []
    if mismatched:
        lines.append("**比率重算對不上**（可能是模型算錯，也可能它引用的期間我們算不出來）：")
        lines += [f"　• {m}" for m in mismatched]

    unexplained = audit_numbers(report, evidence_text)
    if unexplained:
        logger.warning("報告稽核：%d 個數字查不到出處 %s", len(unexplained), unexplained[:10])
        shown = ", ".join(f"{v:,.2f}".rstrip("0").rstrip(".") for v in unexplained[:8])
        more = f"　等 {len(unexplained)} 個" if len(unexplained) > 8 else ""
        if lines:
            lines.append("")
        lines.append(
            "**查不到出處的數字**：以下數字既不在本次資料中，也無法從中"
            f"推算出來，引用前請自行查證：{shown}{more}"
        )

    if not lines:
        return ""
    return "\n\n---\n\n⚠️ **自動稽核**\n\n" + "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# 具名比率的重算
#
# 上面那套「這個數字推不推導得出來」實測幾乎沒有偵測力：台積電的證據包
# 有 46 個數字，兩兩排列會產生 4,428 個推導值，把 0–100 這段數線鋪滿了。
# 把證據包裡的真數字擾動 5–50%（幻覺的典型樣貌）之後，仍有 94% 被判為
# 「算得出來」；一份 4,830 字元的真實報告裡 36 個數字，它標記 0 個。
#
# 問題出在提問的方式。「這個數字有沒有可能是某兩個數字算出來的」在候選
# 集夠大時永遠是「有可能」。改成問「報告說毛利率是 56.1%，那用本次資料
# 算出來的毛利率是多少」——點對點比對，候選只有幾個期間，就有偵測力了。
# ─────────────────────────────────────────────────────────────────────

# (報告裡的寫法, 分子, 分母, 對應的 yfinance 指標)
_RATIO_RULES: tuple[tuple[tuple[str, ...], str, str, str | None], ...] = (
    (("毛利率",), "gross_profit", "revenue", "grossMargins"),
    (("營業利益率", "營益率"), "operating_income", "revenue", "operatingMargins"),
    (("稅後淨利率", "純益率", "淨利率"), "net_income", "revenue", "profitMargins"),
    (("有效稅率",), "tax", "pretax_income", None),
    (("股東權益報酬率", "ROE"), "net_income", "equity", "returnOnEquity"),
    (("資產報酬率", "ROA"), "net_income", "total_assets", None),
    (("負債比率", "負債比"), "total_liabilities", "total_assets", None),
)

_ALIAS = {alias: rule for rule in _RATIO_RULES for alias in rule[0]}

# 長的別名要先比，否則「稅後淨利率」會被「淨利率」先吃掉
_NAMED_RATIO_RE = re.compile(
    "(?P<name>" + "|".join(sorted(_ALIAS, key=len, reverse=True)) + ")"
    r"[^0-9%\n]{0,14}(?P<value>\d+(?:\.\d+)?)\s*%"
)

# 公司財測、分析師預估的比率算不出來也是正常的，不能拿本次資料去對
_FORWARD_LOOKING = re.compile(r"(預期|預估|預計|預測|財測|展望|指引|目標|guidance)")

# 相對誤差與絕對百分點，兩者取寬的。訂寬是刻意的：報告可能引用某一季，
# 而我們只算得出年度與 TTM，期間口徑本來就有差。寧可只抓明顯離譜的，
# 也不要變成一個會亂叫、於是被無視的檢查。
_RATIO_SLACK_REL = 0.05
_RATIO_SLACK_ABS = 1.5


def _series_pairs(annual: dict, num_key: str, den_key: str):
    num, den = annual.get(num_key) or {}, annual.get(den_key) or {}
    for period in sorted(set(num) & set(den)):
        if den[period]:
            yield period, num[period] / den[period] * 100


def _quarter_pairs(quarterly: dict, num_key: str, den_key: str):
    num = {r["date"]: r["value"] for r in (quarterly.get(num_key) or []) if r.get("date")}
    den = {r["date"]: r["value"] for r in (quarterly.get(den_key) or []) if r.get("date")}
    for period in sorted(set(num) & set(den)):
        if den[period] and num[period] is not None:
            yield period, num[period] / den[period] * 100


def ratio_candidates(financials: dict, metrics: dict, name: str) -> list[tuple[str, float]]:
    """這個比率用本次資料能算出哪些值（每個期間一個）。"""
    rule = _ALIAS.get(name)
    if not rule:
        return []
    _, num_key, den_key, metric_key = rule
    out = list(_series_pairs((financials or {}).get("annual") or {}, num_key, den_key))
    out += list(_quarter_pairs((financials or {}).get("quarterly") or {}, num_key, den_key))
    metric = (metrics or {}).get(metric_key) if metric_key else None
    if isinstance(metric, dict) and isinstance(metric.get("value"), (int, float)):
        out.append((metric.get("period") or "TTM", metric["value"] * 100))
    return out


def verify_ratios(report: str, financials: dict, metrics: dict | None = None) -> list[str]:
    """把報告裡的具名比率逐一重算，回傳對不上的那些。

    對不上不代表模型編造——也可能它引用的是我們算不出來的期間。所以
    訊息寫的是「算出來是這些」，讓讀的人自己判斷，不下定論。
    """
    problems = []
    seen = set()
    for m in _NAMED_RATIO_RE.finditer(report or ""):
        name, stated = m.group("name"), float(m.group("value"))
        if _FORWARD_LOOKING.search(report[max(0, m.start() - 40):m.start()]):
            continue
        key = (name, stated)
        if key in seen:
            continue
        candidates = ratio_candidates(financials, metrics, name)
        if not candidates:
            continue
        seen.add(key)
        if any(abs(stated - v) <= max(_RATIO_SLACK_ABS, _RATIO_SLACK_REL * abs(v))
               for _, v in candidates):
            continue
        shown = "、".join(f"{p} {v:.1f}%" for p, v in sorted(candidates, key=lambda x: x[0])[:4])
        problems.append(f"報告寫「{name} {stated:g}%」，但用本次資料重算是 {shown}")
    if problems:
        logger.warning("比率重算對不上：%s", problems)
    return problems
