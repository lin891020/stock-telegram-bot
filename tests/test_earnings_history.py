from bot.handlers.earnings import _format_quarter_history


def _q(date_str, actual=None, estimate=None):
    return {"date": date_str, "eps_actual": actual, "eps_estimate": estimate}


def test_labels_by_report_date_not_guessed_fiscal_quarter():
    """NVDA 五月公布的是 FY2027 Q1，不是 Q12026。

    財年結束月各家不同，光看公布月份推不出財季——舊版對 NVDA/AAPL/MU
    整片標錯。標公布日雖然沒那麼漂亮，但不會錯。
    """
    out = _format_quarter_history([_q("2026-05-20", 0.96, 0.93)], "NVDA")
    assert "2026-05-20 公布" in out
    assert "Q1" not in out


def test_beat_and_miss_percentages():
    out = _format_quarter_history([_q("2026-05-20", 1.10, 1.00)], "NVDA")
    assert "▲ beat" in out and "+10.0%" in out

    out = _format_quarter_history([_q("2026-05-20", 0.90, 1.00)], "NVDA")
    assert "▼ miss" in out and "-10.0%" in out


def test_taiwan_stocks_use_nt_dollar():
    assert "NT$" in _format_quarter_history([_q("2026-05-20", 8.0)], "2330")
    assert "NT$" not in _format_quarter_history([_q("2026-05-20", 8.0)], "AAPL")


def test_unreported_quarter_marked_as_pending():
    out = _format_quarter_history([_q("2026-11-19", None, 1.20)], "NVDA")
    assert "尚未公布" in out


def test_newest_first_and_capped_at_four():
    dates = ["2025-08-27", "2025-11-19", "2026-02-25", "2026-05-20", "2026-08-26"]
    out = _format_quarter_history([_q(d, 1.0, 1.0) for d in dates], "NVDA")
    lines = [ln for ln in out.split("\n") if ln.startswith("•")]
    assert len(lines) == 4
    assert lines[0].startswith("• 2026-08-26")
    assert "2025-08-27" not in out


def test_empty_input_returns_empty_string():
    assert _format_quarter_history([], "NVDA") == ""
    assert _format_quarter_history([{"eps_actual": 1.0}], "NVDA") == ""
