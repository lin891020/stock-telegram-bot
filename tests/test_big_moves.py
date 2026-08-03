import pytest

import bot.services.big_moves as big_moves
from bot.services.big_moves import classify_move, mark_sent, tw_limit_prices, tw_tick, was_sent


@pytest.fixture(autouse=True)
def tmp_state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(big_moves, "_FILE", tmp_path / "big_moves.json")


def test_tw_tick_bands():
    assert tw_tick(9.99) == 0.01
    assert tw_tick(10) == 0.05
    assert tw_tick(49.95) == 0.05
    assert tw_tick(50) == 0.1
    assert tw_tick(100) == 0.5
    assert tw_tick(500) == 1.0
    assert tw_tick(1200) == 5.0


def test_tw_limit_prices_round_inward_by_tick():
    # 1090 → 漲停 1195（1199 要往下取到 5 元檔）、跌停 981
    assert tw_limit_prices(1090) == (1195.0, 981.0)
    # 100 元以下走 0.5 檔
    assert tw_limit_prices(90) == (99.0, 81.0)
    # 小數價位走 0.05 檔：33 → 36.3 / 29.7
    up, down = tw_limit_prices(33)
    assert up == pytest.approx(36.3)
    assert down == pytest.approx(29.7)


def test_tw_limit_up_detected_below_ten_percent():
    # 1195 / 1090 = +9.63%，比 10% 少，但確實是漲停
    move = classify_move("2330", 1195.0, 1090.0)
    assert move["direction"] == "up"
    assert move["headline"] == "漲停"
    assert move["pct"] < 10


def test_tw_limit_down_detected():
    move = classify_move("2330", 981.0, 1090.0)
    assert move["direction"] == "down"
    assert move["headline"] == "跌停"


def test_tw_big_but_not_limit_is_ignored():
    assert classify_move("2330", 1180.0, 1090.0) is None


def test_us_threshold():
    assert classify_move("TSLA", 110.0, 100.0)["direction"] == "up"
    assert classify_move("TSLA", 90.0, 100.0)["direction"] == "down"
    assert classify_move("TSLA", 109.0, 100.0) is None
    assert classify_move("TSLA", 91.0, 100.0) is None


def test_missing_quote_is_ignored():
    assert classify_move("TSLA", None, 100.0) is None
    assert classify_move("TSLA", 110.0, None) is None


def test_dedupe_per_day_and_direction():
    assert not was_sent("1", "2330", "up")
    mark_sent("1", "2330", "up")
    assert was_sent("1", "2330", "up")
    # 另一個方向、另一支、另一個使用者都不受影響
    assert not was_sent("1", "2330", "down")
    assert not was_sent("1", "TSLA", "up")
    assert not was_sent("2", "2330", "up")


def test_state_resets_on_new_day(monkeypatch):
    mark_sent("1", "2330", "up")
    import datetime as real_datetime

    class _Tomorrow(real_datetime.date):
        @classmethod
        def today(cls):
            return real_datetime.date(2999, 1, 1)

    monkeypatch.setattr(big_moves, "date", _Tomorrow)
    assert not was_sent("1", "2330", "up")
