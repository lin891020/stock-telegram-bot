"""報告產出後的數字稽核。

重點不在「抓到編造」，而在**不要把合法推導誤報成編造**。實測一份
台股報告有 17 個數字不在證據包裡，逐一手驗後全部是合法推導
（淨利率、年增率、資產成長率）。只比對「有沒有出現過」的稽核會被
誤報淹沒到沒人看。
"""
import pytest

from bot.services.claim_audit import audit_note, audit_numbers, extract_numbers

# 台積電那份報告的證據包（真實數字節錄）
EVIDENCE = """
營收：2024: 2894307699000　2025: 3809054272000
稅後淨利：2024: 1172431759000　2025: 1715396780000
總資產：2024: 6690000000000　2026: 9380000000000
毛利率 64.23　營業利益率 60.34　淨利率 49.92
本益比 28.33　目標價 3229.33　現價 2420.00
"""


def test_growth_rates_are_not_flagged():
    """31.8% = 3.81兆 ÷ 2.89兆 − 1，是合法推導不是編造。"""
    assert audit_numbers("2025 營收年增 31.8%", EVIDENCE) == []


def test_margins_are_not_flagged():
    """40.5% = 1.17兆 ÷ 2.89兆。"""
    assert audit_numbers("2024 淨利率 40.5%", EVIDENCE) == []


def test_rounding_is_tolerated():
    """報告會四捨五入（31.83 寫成 31.8），太嚴會全是誤報。"""
    assert audit_numbers("年增 31.8%，資產成長 40%", EVIDENCE) == []


def test_fabricated_numbers_are_flagged():
    flagged = audit_numbers("研發費用 8,888 億元，員工 77,777 人", EVIDENCE)
    assert 8888.0 in flagged and 77777.0 in flagged


def test_mixed_report_flags_only_the_fabrication():
    flagged = audit_numbers("淨利率由 40.5% 升至 45.1%，研發費用 8,888 億元", EVIDENCE)
    assert flagged == [8888.0]


def test_numbers_quoted_verbatim_are_fine():
    assert audit_numbers("本益比 28.33，現價 2,420.00", EVIDENCE) == []


def test_years_and_small_numbers_are_ignored():
    """年份與個位數不值得追。"""
    nums = extract_numbers("2024 年第 3 季，共 5 項")
    assert 2024 not in nums and 3 not in nums and 5 not in nums


def test_note_is_empty_when_everything_checks_out():
    assert audit_note("淨利率 40.5%", EVIDENCE) == ""


def test_note_names_the_numbers():
    note = audit_note("研發費用 8,888 億元", EVIDENCE)
    assert "自動稽核" in note and "8,888" in note
    assert "請自行查證" in note


def test_no_evidence_means_no_audit():
    """證據包是空的時候不稽核——會把整份報告都標記，等於沒說。"""
    assert audit_numbers("隨便什麼 12,345", "") == []


# ── 具名比率的重算 ────────────────────────────────────────────────────
# 舊的「推不推導得出來」實測誤放率 94%（見 _derivations 的註解）。
# 這幾個測試鎖住取而代之的那一層。

_FIN = {
    "annual": {
        "revenue": {"2024": 1000.0, "2025": 1200.0},
        "gross_profit": {"2024": 560.0, "2025": 720.0},
        "operating_income": {"2024": 450.0, "2025": 600.0},
        "net_income": {"2024": 400.0, "2025": 540.0},
        "pretax_income": {"2024": 480.0, "2025": 640.0},
        "tax": {"2024": 80.0, "2025": 100.0},
        "total_assets": {"2024": 2000.0, "2025": 2400.0},
        "total_liabilities": {"2024": 700.0, "2025": 720.0},
        "equity": {"2024": 1300.0, "2025": 1680.0},
    },
    "quarterly": {},
}
_MT = {"grossMargins": {"label": "毛利率", "value": 0.58, "period": "TTM"}}


def test_correct_ratio_passes():
    """56.0%（2024）與 60.0%（2025）都算得出來，不該叫。"""
    from bot.services.claim_audit import verify_ratios
    assert verify_ratios("毛利率 56.0%，2025 年為 60.0%", _FIN, _MT) == []


def test_fabricated_ratio_is_caught():
    from bot.services.claim_audit import verify_ratios
    problems = verify_ratios("毛利率高達 82.0%", _FIN, _MT)
    assert len(problems) == 1
    assert "82" in problems[0] and "56.0%" in problems[0]


def test_forward_guidance_is_exempt():
    """公司財測的毛利率本來就算不出來，拿本次資料去對是誤報。

    實測 NVDA 的財報速覽就寫「財測：⋯毛利率預期為 74.0%」。
    """
    from bot.services.claim_audit import verify_ratios
    assert verify_ratios("公司預期下季毛利率為 74.0%", _FIN, _MT) == []
    assert verify_ratios("財測毛利率 74.0%", _FIN, _MT) == []


def test_longer_alias_wins():
    """「稅後淨利率」不可以被「淨利率」先吃掉。"""
    from bot.services.claim_audit import verify_ratios
    problems = verify_ratios("稅後淨利率 90.0%", _FIN, None)
    assert problems and "稅後淨利率" in problems[0]


def test_ratio_without_data_is_not_guessed():
    """算不出來的比率就不評論，不能因為對不上就標記。"""
    from bot.services.claim_audit import verify_ratios
    assert verify_ratios("ROE 為 33.0%", {"annual": {}}, None) == []


def test_liabilities_ratio_needs_the_fixed_finmind_names():
    """負債比率要靠 total_liabilities／equity，而台股那兩欄曾經一直是空的。"""
    from bot.services.claim_audit import ratio_candidates
    assert dict(ratio_candidates(_FIN, None, "負債比率"))["2025"] == pytest.approx(30.0)
    assert dict(ratio_candidates(_FIN, None, "ROE"))["2025"] == pytest.approx(540 / 1680 * 100)


def test_note_reports_ratio_mismatch():
    note = audit_note("毛利率 82.0%", "營收 1000", _FIN, _MT)
    assert "自動稽核" in note and "比率重算對不上" in note


def test_note_without_financials_skips_ratio_check():
    """沒傳財報就只做舊的那層，不能因此炸掉，也不能假裝重算過。"""
    note = audit_note("毛利率 82.0%", "營收 1000")
    assert "比率重算" not in note
