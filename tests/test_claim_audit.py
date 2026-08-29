"""報告產出後的數字稽核。

重點不在「抓到編造」，而在**不要把合法推導誤報成編造**。實測一份
台股報告有 17 個數字不在證據包裡，逐一手驗後全部是合法推導
（淨利率、年增率、資產成長率）。只比對「有沒有出現過」的稽核會被
誤報淹沒到沒人看。
"""
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
