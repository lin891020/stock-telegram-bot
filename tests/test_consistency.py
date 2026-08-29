"""資料層健全性檢查。

抓的是「數字在證據包裡，但它是錯的」——這類錯對模型和證據包都是
隱形的，模型只會忠實地引用一個假數字。
"""
from bot.services.consistency import (
    check_balance_identity, check_capex_sign, check_cashflow_scale,
    check_cross_source, check_financials, check_income_ordering, check_tax_identity,
)

# 台積電 2024 的真實數字
_GOOD = {
    "revenue": {"2024": 2_894_307_699_000},
    "gross_profit": {"2024": 1_624_300_000_000},
    "operating_income": {"2024": 1_320_000_000_000},
    "net_income": {"2024": 1_172_431_759_000},
    "operating_cashflow": {"2024": 1_826_177_068_000},
    "capex": {"2024": -956_000_000_000},
    "total_assets": {"2024": 6_690_000_000_000},
    "total_liabilities": {"2024": 2_400_000_000_000},
    "equity": {"2024": 4_290_000_000_000},
}


def test_real_numbers_raise_nothing():
    assert check_financials({"annual": _GOOD}) == []


def test_catches_the_cumulative_cashflow_bug():
    """今天實際踩到的那個：FinMind 的現金流是累計數，被當單季加總。

    營業現金流 4.28 兆 > 全年營收 2.89 兆，製造業不可能。
    """
    bad = {**_GOOD, "operating_cashflow": {"2024": 4_283_000_000_000}}
    notes = check_cashflow_scale(bad)
    assert len(notes) == 1
    assert "累計數" in notes[0] and "不要引用" in notes[0]


def test_catches_broken_income_ordering():
    """營收 ≥ 毛利 ≥ 營業利益，這兩段才是恆等式。"""
    bad = {**_GOOD, "gross_profit": {"2024": 3_000_000_000_000}}   # 毛利 > 營收
    notes = check_income_ordering(bad)
    assert notes and "會計上不可能" in notes[0]


# 聯發科 2025 的真實數字：淨利大於營業利益，但完全正確
_MTK_2025 = {
    "revenue": {"2025": 595_966_000_000},
    "gross_profit": {"2025": 300_000_000_000},
    "operating_income": {"2025": 103_469_695_000},
    "pretax_income": {"2025": 124_900_000_000},
    "tax": {"2025": 18_800_000_000},
    "net_income": {"2025": 106_117_575_000},
}


def test_net_income_above_operating_income_is_not_an_error():
    """「營業利益 ≥ 淨利」不是恆等式——業外收入大於所得稅時就會反轉。

    聯發科 2025：營業利益 1,035 億、業外 +214 億、稅 −188 億、淨利 1,061 億。
    這條規則曾經對九支自選股裡的兩支誤報，而會亂叫的檢查只會被忽略。
    """
    assert check_income_ordering(_MTK_2025) == []
    assert check_financials({"annual": _MTK_2025}) == []


def test_tax_identity_holds_for_real_data():
    """稅後淨利 = 稅前淨利 − 所得稅，這才是真正的恆等式。"""
    assert check_tax_identity(_MTK_2025) == []


def test_tax_identity_catches_mismatched_periods():
    bad = {**_MTK_2025, "net_income": {"2025": 150_000_000_000}}
    notes = check_tax_identity(bad)
    assert notes and "不等於稅前淨利減所得稅" in notes[0]


def test_net_income_above_revenue_is_flagged():
    bad = {**_GOOD, "net_income": {"2024": 5_000_000_000_000}}
    notes = check_income_ordering(bad)
    assert any("大於營收" in n for n in notes)


def test_catches_unbalanced_balance_sheet():
    bad = {**_GOOD, "equity": {"2024": 1_000_000_000_000}}
    notes = check_balance_identity(bad)
    assert notes and "不平衡" in notes[0]


def test_catches_positive_capex():
    """資本支出是現金流出，正數代表科目抓錯。"""
    bad = {**_GOOD, "capex": {"2024": 956_000_000_000}}
    assert check_capex_sign(bad)


def test_catches_cross_source_magnitude_gap():
    """FinMind 與 yfinance 差三倍以上就是量級錯誤。"""
    notes = check_cross_source(_GOOD, {"totalRevenue": 500_000_000_000})
    assert notes and "至少有一個是錯的" in notes[0]


def test_tolerates_normal_cross_source_differences():
    """TTM vs 年度、合併 vs 母公司本來就有落差，不該每次都叫。"""
    assert check_cross_source(_GOOD, {"totalRevenue": 3_400_000_000_000}) == []


def test_partial_years_are_skipped():
    """「僅 2 季合計」不是全年，拿去跟全年比會誤報。"""
    partial = {
        "revenue": {"2026（僅 2 季合計，非全年）": 2_404_483_690_000},
        "operating_cashflow": {"2026（截至 06-30 累計，非全年）": 1_482_341_242_000},
    }
    assert check_financials({"annual": partial}) == []


def test_missing_data_is_not_an_error():
    assert check_financials({}) == []
    assert check_financials({"annual": {}}) == []


def test_problems_reach_the_evidence_pack():
    """檢查結果要真的餵進 prompt，否則模型看不到。"""
    from bot.services.evidence import build_evidence
    bad = {"annual": {**_GOOD, "operating_cashflow": {"2024": 4_283_000_000_000}}}
    ev = build_evidence("2330", "financial", {"name": "台積電"}, bad, {})
    assert any("資料自我矛盾" in n for n in ev.notes)
    assert "累計數" in ev.to_prompt()
