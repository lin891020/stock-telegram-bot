import pytest

from bot.services.evidence import (
    FIN_ANNUAL, QUOTE, REQUIREMENTS, SUBJECTIVE_NOTES, build_evidence,
)
from bot.services.metrics import check_margin_consistency, extract_metrics, format_metric

STOCK = {"name": "NVIDIA", "price": 206.64, "prev_close": 200.76, "market": "US", "date": "2026-08-04"}
FIN = {
    "market": "US",
    "annual": {"revenue": {"2025": 1.3e11}, "net_income": {"2025": 7.3e10}},
    "quarterly": {"revenue": [{"date": "2026-04-26", "value": 4.4e10}]},
}
INFO = {
    "longName": "NVIDIA Corp", "trailingPE": 33.686, "forwardPE": 17.06,
    "grossMargins": 0.74145, "returnOnEquity": 1.14288, "targetMeanPrice": 302.83,
    "numberOfAnalystOpinions": 58, "recommendationKey": "strong_buy",
    "priceToBook": 27.26, "revenueGrowth": 0.852, "earningsGrowth": 2.145,
}


def _ev(key, stock=STOCK, fin=FIN, info=INFO):
    metrics, anomalies = extract_metrics(info)
    return build_evidence("NVDA", key, stock, fin, metrics, anomalies)


def test_format_metric_kinds():
    assert format_metric(0.74145, "pct") == "74.15%"
    assert format_metric(33.686, "num") == "33.69"
    assert format_metric(58, "int") == "58"
    assert format_metric(4.6e10, "money") == "460.00億"
    assert format_metric("strong_buy", "text") == "strong_buy"


def test_extract_metrics_skips_absent_fields():
    m, _ = extract_metrics({"trailingPE": 33.686})
    assert set(m) == {"trailingPE"}
    assert m["trailingPE"]["display"] == "33.69"
    assert m["trailingPE"]["source"] == "yfinance"
    # 缺的欄位不補 N/A、不補預設值
    assert "targetMeanPrice" not in extract_metrics({})[0]


def test_facts_carry_source():
    ev = _ev("valuation")
    assert ev.has(QUOTE) and ev.has(FIN_ANNUAL) and ev.has("trailingPE")
    prompt = ev.to_prompt()
    assert "[來源：yfinance]" in prompt
    assert "本益比（TTM）：33.69" in prompt


def test_unavailable_requirements_always_reported_missing():
    """已知沒有資料源的需求（同業估值、DCF）必定進缺漏，即使其他資料齊全。"""
    ev = _ev("valuation")
    assert "同業估值對照數據" in ev.missing
    assert any("DCF" in m for m in ev.missing)
    # 有抓到的就不該進缺漏
    assert not any("分析師目標價" in m for m in ev.missing)


def test_missing_metric_lands_in_missing_list():
    ev = _ev("valuation", info={"longName": "NVIDIA Corp"})  # 完全沒有指標
    assert any("估值指標" in m for m in ev.missing)
    assert any("分析師目標價" in m for m in ev.missing)


def test_financials_error_becomes_note_not_licence_to_invent():
    ev = _ev("financial", fin={"error": "FinMind 無法取得 2330 財報資料"})
    assert not ev.has(FIN_ANNUAL)
    assert any("財務報表抓取失敗" in n for n in ev.notes)
    assert "年度財務報表" in ev.missing
    # 缺漏區必須明文禁止用記憶填補
    assert "不得推測" in ev.to_prompt()


def test_subjective_types_get_note():
    assert "護城河" in "".join(_ev("moat").notes)
    assert "推論" in "".join(_ev("debate").notes)


def test_moat_has_no_quantitative_source():
    ev = _ev("moat")
    assert any("量化" in m for m in ev.missing)
    assert any("市占率" in m for m in ev.missing)


def test_prompt_states_when_nothing_missing():
    ev = build_evidence("NVDA", "unknown_key", STOCK, FIN, extract_metrics(INFO)[0])
    assert ev.missing == []
    assert "本次所需資料齊全" in ev.to_prompt()


def test_missing_block_empty_when_complete():
    ev = build_evidence("NVDA", "unknown_key", STOCK, FIN, extract_metrics(INFO)[0])
    assert ev.missing_block() == ""
    assert "本次無法取得" in _ev("valuation").missing_block()


@pytest.mark.parametrize("key", sorted(REQUIREMENTS))
def test_every_analysis_type_declares_requirements(key):
    ev = _ev(key)
    assert ev.facts, f"{key} 應該至少有事實"
    # 每種類型都該誠實承認至少一項拿不到的東西
    assert ev.missing, f"{key} 沒有任何缺漏，需求表可能漏定義"


def test_subjective_keys_are_known_analysis_types():
    assert set(SUBJECTIVE_NOTES) <= set(REQUIREMENTS)


def test_inconsistent_margins_are_dropped_wholesale():
    """實測 2408：營益率 73.68% > 毛利率 64.91%，會計上不可能。
    分不出哪個錯，就一個都不能用。"""
    bad = {"grossMargins": 0.64911, "operatingMargins": 0.73685, "profitMargins": 0.49254}
    problems = check_margin_consistency(bad)
    assert problems and "違反會計恆等關係" in problems[0]
    metrics, anomalies = extract_metrics({**INFO, **bad})
    assert not {"grossMargins", "operatingMargins", "profitMargins"} & set(metrics)
    assert anomalies
    # 其他指標不受牽連
    assert "trailingPE" in metrics


def test_consistent_margins_are_kept():
    good = {"grossMargins": 0.48653, "operatingMargins": 0.32623, "profitMargins": 0.27619}
    assert check_margin_consistency(good) == []
    metrics, anomalies = extract_metrics(good)
    assert set(metrics) == set(good)
    assert anomalies == []


def test_anomalies_surface_as_notes():
    bad = {"grossMargins": 0.64911, "operatingMargins": 0.73685}
    metrics, anomalies = extract_metrics({**INFO, **bad})
    ev = build_evidence("2408", "financial", STOCK, FIN, metrics, anomalies)
    assert any("資料源異常" in n for n in ev.notes)
    # 利潤率被剔除 → 需求落入缺漏
    assert any("獲利能力指標" in m for m in ev.missing)


def test_debt_label_is_not_total_liabilities():
    """totalDebt 只是借款，標成「總負債」會讓模型算出假的淨現金部位。"""
    metrics, _ = extract_metrics({"totalDebt": 84_344_000_000})
    label = metrics["totalDebt"]["label"]
    assert "有息負債" in label
    assert label != "總負債"
