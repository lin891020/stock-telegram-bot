"""資料層的健全性檢查：抓「數字在證據包裡，但它是錯的」這一類。

證據包解決的是「模型別亂編」，但它擋不住我們自己餵錯數字——那種錯
對模型和證據包都是隱形的，模型只會忠實地引用一個假數字。

實際踩到的：FinMind 的損益表是單季數（要加總）、現金流量表是年初
至今累計數（不能加總），同一個 API 兩種語意且沒有欄位標明。程式對
兩者都加總，台積電 2024 營業現金流被算成 4.28 兆，真實是 1.83 兆。

那個錯有跡可循：營業現金流 (4.28兆) 竟然大於全年營收 (2.89兆)。
下面的檢查就是把這類「說不通」寫成程式看得懂的規則。

原則跟證據包一致：**只標記，不猜哪個對**。兩個來源打架時我們無從
判斷誰對，但可以明講「這兩個數字至少有一個是錯的，不要引用」。
"""
import logging

logger = logging.getLogger(__name__)

# 兩個來源差幾倍以上才算「打架」。財報期間口徑本來就會有差異
# （TTM vs 年度、合併 vs 母公司），倍數訂寬一點只抓真正的量級錯誤。
_MAGNITUDE_RATIO = 3.0


def _latest_full_year(series: dict) -> tuple[str, float] | None:
    """取最近一個完整年度（鍵名沒有「非全年」標記的）。"""
    full = {k: v for k, v in (series or {}).items() if "非全年" not in k}
    if not full:
        return None
    key = max(full)
    return key, full[key]


def _ratio(a: float, b: float) -> float:
    lo, hi = sorted((abs(a), abs(b)))
    return hi / lo if lo else float("inf")


def check_income_ordering(annual: dict) -> list[str]:
    """損益表的大小關係：營收 ≥ 毛利 ≥ 營業利益。

    這兩段才是真正的恆等式：
      毛利 = 營收 − 銷貨成本（成本 ≥ 0）
      營業利益 = 毛利 − 營業費用（費用 ≥ 0）

    ⚠️ 「營業利益 ≥ 稅後淨利」**不是**恆等式，不要加進來。業外收入
    （利息、投資收益、匯兌）大於所得稅時，淨利就會大於營業利益。
    實測聯發科 2025：營業利益 1,035 億、業外 +214 億、稅 −188 億、
    淨利 1,061 億——完全正確的數字。這條規則曾經對九支自選股裡的
    兩支誤報，而會亂叫的檢查只會訓練人忽略它。
    """
    chain = [
        ("營收", "revenue"),
        ("毛利", "gross_profit"),
        ("營業利益", "operating_income"),
    ]
    values = []
    for label, key in chain:
        got = _latest_full_year(annual.get(key, {}))
        if got:
            values.append((label, got[0], got[1]))

    notes = []
    for (la, ya, va), (lb, yb, vb) in zip(values, values[1:]):
        if ya != yb or va < 0 or vb < 0:
            continue
        if vb > va:
            notes.append(
                f"{yb} 年的{lb}（{vb:,.0f}）大於{la}（{va:,.0f}），"
                f"會計上不可能——這兩項至少有一個的期間或加總方式是錯的，不要引用"
            )

    # 淨利大於營收才是真正異常（業外再多也很難超過整年營收）
    rev = _latest_full_year(annual.get("revenue", {}))
    net = _latest_full_year(annual.get("net_income", {}))
    if rev and net and rev[0] == net[0] and rev[1] > 0 and net[1] > rev[1]:
        notes.append(
            f"{net[0]} 年的稅後淨利（{net[1]:,.0f}）大於營收（{rev[1]:,.0f}），"
            f"極不尋常——兩項的期間或加總方式可能不一致，不要引用"
        )
    return notes


def check_tax_identity(annual: dict) -> list[str]:
    """稅後淨利 = 稅前淨利 − 所得稅。這是真正的恆等式。

    比「營業利益 ≥ 淨利」有用得多：它能抓出三個科目之間期間或加總
    方式不一致的情況，而不會被業外收入誤導。
    """
    got = [
        _latest_full_year(annual.get(k, {}))
        for k in ("pretax_income", "tax", "net_income")
    ]
    if any(g is None for g in got):
        return []
    (yp, pretax), (yt, tax), (yn, net) = got
    if not (yp == yt == yn) or pretax == 0:
        return []
    expected = pretax - tax
    if abs(expected - net) / abs(pretax) > 0.02:
        return [
            f"{yn} 年的稅後淨利（{net:,.0f}）不等於稅前淨利減所得稅"
            f"（{pretax:,.0f} − {tax:,.0f} = {expected:,.0f}）——"
            f"三個科目的期間或加總方式不一致，不要引用"
        ]
    return []


def check_cashflow_scale(annual: dict) -> list[str]:
    """營業現金流不該大於同年營收。

    製造業幾乎不可能：現金流來自營收的收現，扣掉成本費用只會更小。
    這正是 FinMind 累計數被加總後露出的破綻（4.28兆 > 2.89兆）。
    """
    rev = _latest_full_year(annual.get("revenue", {}))
    ocf = _latest_full_year(annual.get("operating_cashflow", {}))
    if not rev or not ocf or rev[0] != ocf[0] or rev[1] <= 0:
        return []
    if ocf[1] > rev[1]:
        return [
            f"{ocf[0]} 年的營業現金流（{ocf[1]:,.0f}）大於營收（{rev[1]:,.0f}），"
            f"高度可疑——可能把年初至今的累計數當成單季加總了，不要引用現金流數字"
        ]
    return []


def check_balance_identity(annual: dict) -> list[str]:
    """資產 = 負債 + 權益。差超過 2% 就代表某一項抓錯科目。"""
    got = [
        _latest_full_year(annual.get(k, {}))
        for k in ("total_assets", "total_liabilities", "equity")
    ]
    if any(g is None for g in got):
        return []
    (ya, assets), (yl, liab), (ye, eq) = got
    if not (ya == yl == ye) or assets <= 0:
        return []
    gap = abs(assets - (liab + eq)) / assets
    if gap > 0.02:
        return [
            f"{ya} 年的資產（{assets:,.0f}）與負債＋權益（{liab + eq:,.0f}）"
            f"相差 {gap:.1%}，資產負債表不平衡——三項至少有一項抓錯科目"
        ]
    return []


def check_cross_source(annual: dict, metrics: dict) -> list[str]:
    """FinMind（台股財報）與 yfinance（同一家公司）的量級對照。

    兩邊口徑本來就不同，只抓差三倍以上的量級錯誤。
    """
    notes = []
    pairs = [
        ("營收", "revenue", "totalRevenue"),
        ("稅後淨利", "net_income", "netIncomeToCommon"),
    ]
    for label, fin_key, yf_key in pairs:
        got = _latest_full_year(annual.get(fin_key, {}))
        raw = (metrics.get(yf_key) or {}).get("raw") if isinstance(metrics.get(yf_key), dict) else metrics.get(yf_key)
        if not got or not isinstance(raw, (int, float)) or raw == 0:
            continue
        if _ratio(got[1], raw) >= _MAGNITUDE_RATIO:
            notes.append(
                f"{label}在兩個來源差了 {_ratio(got[1], raw):.1f} 倍"
                f"（FinMind {got[0]}：{got[1]:,.0f}／yfinance：{raw:,.0f}）"
                f"——至少有一個是錯的，不要引用"
            )
    return notes


def check_capex_sign(annual: dict) -> list[str]:
    """資本支出是現金流出，應為負數。變正數代表科目抓錯。"""
    got = _latest_full_year(annual.get("capex", {}))
    if got and got[1] > 0:
        return [f"{got[0]} 年的資本支出是正數（{got[1]:,.0f}），"
                f"但它應該是現金流出——科目可能抓錯"]
    return []


def check_financials(financials: dict, metrics: dict | None = None) -> list[str]:
    """跑完所有資料層檢查，回傳人話的問題清單（沒問題就是空的）。"""
    annual = (financials or {}).get("annual") or {}
    if not annual:
        return []
    notes = []
    for check in (check_income_ordering, check_tax_identity, check_cashflow_scale,
                  check_balance_identity, check_capex_sign):
        try:
            notes += check(annual)
        except Exception as e:
            logger.warning("資料層檢查 %s 失敗：%s", check.__name__, e)
    if metrics:
        try:
            notes += check_cross_source(annual, metrics)
        except Exception as e:
            logger.warning("跨來源檢查失敗：%s", e)
    if notes:
        logger.warning("資料層檢查發現 %d 個問題：%s", len(notes), notes)
    return notes
