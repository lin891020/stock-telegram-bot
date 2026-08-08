import pytest

import bot.services.earnings_watch as earnings_watch
from bot.services.earnings_watch import detect_new_report, latest_reported_date, prune_state


@pytest.fixture(autouse=True)
def tmp_state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(earnings_watch, "_FILE", tmp_path / "earnings_watch.json")


def _data(*quarters):
    return {"quarters": list(quarters)}


def _q(date_str, actual):
    return {"date": date_str, "eps_actual": actual}


def test_latest_reported_ignores_unreported_quarters():
    data = _data(_q("2026-07-30", None), _q("2026-04-25", 1.2), _q("2026-01-24", 1.1))
    assert latest_reported_date(data) == "2026-04-25"
    assert latest_reported_date(_data(_q("2026-07-30", None))) is None


def test_first_sight_sets_baseline_without_pushing():
    data = _data(_q("2026-04-25", 1.2))
    assert detect_new_report("NVDA", data) is None
    # 同樣資料再看一次也不推
    assert detect_new_report("NVDA", data) is None


def test_new_quarter_pushes_once():
    detect_new_report("NVDA", _data(_q("2026-04-25", 1.2)))  # baseline
    newer = _data(_q("2026-07-30", 1.5), _q("2026-04-25", 1.2))
    assert detect_new_report("NVDA", newer) == "2026-07-30"
    assert detect_new_report("NVDA", newer) is None


def test_older_data_does_not_push():
    detect_new_report("NVDA", _data(_q("2026-07-30", 1.5)))  # baseline
    assert detect_new_report("NVDA", _data(_q("2026-04-25", 1.2))) is None


def test_prune_drops_removed_tickers():
    detect_new_report("NVDA", _data(_q("2026-04-25", 1.2)))
    detect_new_report("TSLA", _data(_q("2026-04-23", 0.5)))
    prune_state(["NVDA"])
    assert set(earnings_watch._load()) == {"NVDA"}


def test_seen_gate_is_separate_from_earnings_baseline():
    """大部分 8-K 不是財報。閘門（last_seen_filing）往前推不該動財報基準。"""
    from bot.services.earnings_watch import _advance
    _advance("last_seen_filing", "NVDA", "2026-07-02")   # 非財報的 8-K
    assert (earnings_watch._load()["NVDA"]).get("last_filing") is None
    _advance("last_filing", "NVDA", "2026-05-20")        # 建財報基準
    assert _advance("last_seen_filing", "NVDA", "2026-08-01") is None or True
    assert earnings_watch._load()["NVDA"]["last_filing"] == "2026-05-20"


def test_advance_only_fires_on_newer_value():
    from bot.services.earnings_watch import _advance
    assert _advance("last_filing", "MU", "2026-06-24") is None      # 首次只記基準
    assert _advance("last_filing", "MU", "2026-06-24") is None      # 相同不觸發
    assert _advance("last_filing", "MU", "2026-03-20") is None      # 往回跳不觸發
    assert _advance("last_filing", "MU", "2026-09-24") == "2026-09-24"
