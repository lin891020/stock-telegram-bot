"""鎖住兩個讓報告寫出假數字的迴歸。

實測 /analyze 2408 產出的報告把南亞科寫成聯電，並宣稱「三年營收成長 12.56 倍」，
兩者都是程式餵了錯誤前提造成的，不是模型亂講。
"""
import pytest

from bot.services.financials import _annual_flow, _annual_point
from bot.services.evidence import NAME, build_evidence


def _rows(*pairs):
    return [{"date": d, "value": v} for d, v in pairs]


def test_flow_items_sum_quarters_not_take_latest():
    """FinMind 給的是單季；年度必須加總，取最後一季等於拿一季冒充整年。"""
    rows = _rows(
        ("2025-03-31", 100), ("2025-06-30", 200),
        ("2025-09-30", 300), ("2025-12-31", 400),
    )
    assert _annual_flow(rows, "value") == {"2025": 1000}


def test_incomplete_year_is_labelled():
    rows = _rows(("2026-03-31", 490.87), ("2026-06-30", 825.49))
    result = _annual_flow(rows, "value")
    key = next(iter(result))
    assert result[key] == pytest.approx(1316.36)
    # 標籤必須讓模型看得出這不是整年，否則會拿它跟完整年度比
    assert key == "2026（僅 2 季合計，非全年）"


def test_point_items_take_latest_not_sum():
    """總資產是存量，四季加總會變成四倍。"""
    rows = _rows(
        ("2025-03-31", 1000), ("2025-06-30", 1100),
        ("2025-09-30", 1200), ("2025-12-31", 1300),
    )
    assert _annual_point(rows, "value") == {"2025": 1300}


def test_point_item_mid_year_is_labelled():
    rows = _rows(("2026-03-31", 3000), ("2026-06-30", 3877.58))
    assert _annual_point(rows, "value") == {"2026（截至 06-30）": 3877.58}


def test_only_three_most_recent_years_kept():
    rows = []
    for year in (2022, 2023, 2024, 2025):
        rows += _rows(*[(f"{year}-{m}", 1) for m in ("03-31", "06-30", "09-30", "12-31")])
    assert sorted(_annual_flow(rows, "value")) == ["2023", "2024", "2025"]


def test_non_numeric_values_ignored():
    rows = [{"date": "2025-03-31", "value": "abc"}, {"date": "2025-06-30", "value": 50}]
    assert _annual_flow(rows, "value") == {"2025（僅 1 季合計，非全年）": 50}


def test_company_name_is_a_fact():
    """少了名稱，模型只拿到代號，會從記憶猜公司——實測猜錯過。"""
    ev = build_evidence(
        "2408", "full",
        {"name": "南亞科", "price": 457.0, "market": "TW"}, {}, {},
    )
    assert ev.has(NAME)
    assert "南亞科" in ev.to_prompt()


def test_missing_name_forbids_guessing():
    ev = build_evidence("2408", "full", {"price": 457.0, "market": "TW"}, {}, {})
    assert not ev.has(NAME)
    assert any("不得自行推測是哪一家公司" in m for m in ev.missing)


# ---- 累計數 vs 單季數：FinMind 同一個 API 兩種語意 ----------------------

def _rows(pairs):
    return [{"date": d, "value": v} for d, v in pairs]


# 台積電 2024 營業現金流的真實形狀：年初至今累計
_TSMC_OCF_2024 = [
    ("2024-03-31", 436_300_000_000),
    ("2024-06-30", 814_000_000_000),
    ("2024-09-30", 1_206_000_000_000),
    ("2024-12-31", 1_826_177_068_000),
]


def test_cumulative_takes_last_period_not_the_sum():
    """現金流量表是年初至今累計，四列相加會虛報 2.3 倍。

    實測：加總得 4.28 兆，真實全年 1.83 兆。每份台股分析都吃到過。
    """
    from bot.services.financials import _annual_cumulative
    out = _annual_cumulative(_rows(_TSMC_OCF_2024), "value")
    assert out["2024"] == 1_826_177_068_000


def test_flow_sums_because_income_statement_is_per_quarter():
    """損益表是單季數，要加總才是年度。

    它看起來也像逐列遞增，那只是公司剛好每季成長——四季相加
    2.89 兆正好等於台積電實際的 2024 全年營收。
    """
    from bot.services.financials import _annual_flow
    rows = _rows([
        ("2024-03-31", 592_600_000_000),
        ("2024-06-30", 673_500_000_000),
        ("2024-09-30", 759_700_000_000),
        ("2024-12-31", 868_500_000_000),
    ])
    assert _annual_flow(rows, "value")["2024"] == 2_894_300_000_000


def test_partial_year_cumulative_is_labelled():
    """半年只有兩列，最後一列就是上半年累計——標明不是全年。"""
    from bot.services.financials import _annual_cumulative
    out = _annual_cumulative(_rows(_TSMC_OCF_2024[:2]), "value")
    key = next(iter(out))
    assert "截至 06-30 累計" in key and "非全年" in key
    assert out[key] == 814_000_000_000


def test_cumulative_and_flow_disagree_on_the_same_input():
    """同一份資料兩種讀法差很多——所以挑錯函式是靜默的錯誤。"""
    from bot.services.financials import _annual_cumulative, _annual_flow
    rows = _rows(_TSMC_OCF_2024)
    assert _annual_flow(rows, "value")["2024"] / _annual_cumulative(rows, "value")["2024"] > 2.3
