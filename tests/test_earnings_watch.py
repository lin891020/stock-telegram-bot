import pytest

import bot.services.earnings_watch as earnings_watch
from bot.services.earnings_watch import (
    commit_event, detect_new_report, latest_reported_date, prune_state,
)


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
    assert detect_new_report("NVDA", data) is None


def test_new_quarter_detected_until_committed():
    """偵測不再自己推進基準——推進要等推播成功。

    以前偵測時就寫死基準，接下來的 build_brief 一出錯（LLM 逾時、SEC 限流），
    那一季的財報就永遠不會再被推播。
    """
    detect_new_report("NVDA", _data(_q("2026-04-25", 1.2)))  # baseline
    newer = _data(_q("2026-07-30", 1.5), _q("2026-04-25", 1.2))

    assert detect_new_report("NVDA", newer) == "2026-07-30"
    # 還沒 commit（等同推播失敗）→ 下一輪仍要能再試
    assert detect_new_report("NVDA", newer) == "2026-07-30"

    commit_event("NVDA", "2026-07-30")
    assert detect_new_report("NVDA", newer) is None


def test_commit_advances_both_signals():
    """SEC 與 EPS 講的是同一季，但基準各記各的。

    只推進觸發的那一條，另一條下一輪會對同一季再推一次——
    實測 SEC 先推、一小時後 EPS 又推了一次。
    """
    for field in ("last_filing", "last_seen_filing", "last_reported"):
        earnings_watch._set(field, "NVDA", "2026-05-20")

    # SEC 訊號觸發並推播成功
    assert earnings_watch._is_new("last_filing", "NVDA", "2026-08-26") is True
    commit_event("NVDA", "2026-08-26")

    # 之後 yfinance 才更新 EPS：不該再推一次
    assert detect_new_report("NVDA", _data(_q("2026-08-26", 1.5))) is None


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
    earnings_watch._set("last_seen_filing", "NVDA", "2026-07-02")
    assert (earnings_watch._load()["NVDA"]).get("last_filing") is None


def test_is_new_only_fires_on_newer_value():
    assert earnings_watch._is_new("last_filing", "MU", "2026-06-24") is False  # 首次只記基準
    assert earnings_watch._is_new("last_filing", "MU", "2026-06-24") is False  # 相同不觸發
    assert earnings_watch._is_new("last_filing", "MU", "2026-03-20") is False  # 往回跳不觸發
    assert earnings_watch._is_new("last_filing", "MU", "2026-09-24") is True
