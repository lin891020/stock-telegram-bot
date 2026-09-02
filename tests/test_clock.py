"""時區換算的測試。

這裡鎖住的是一個真的踩到過的位移：週末判斷若用 UTC，台北清晨的排程
會落在 UTC 的前一天，於是星期一不推、星期六反而推。
"""
from datetime import datetime, time, timezone

import pytest

from bot.services import clock


def _at(monkeypatch, iso: str):
    """把「現在的台北時間」固定成指定值。"""
    fixed = datetime.fromisoformat(iso).replace(tzinfo=clock.TAIPEI)
    monkeypatch.setattr(clock, "now", lambda: fixed)


@pytest.mark.parametrize("iso,weekend", [
    ("2026-01-19T07:00", False),   # 一
    ("2026-01-23T07:00", False),   # 五
    ("2026-01-24T07:00", True),    # 六
    ("2026-01-25T23:59", True),    # 日
    ("2026-01-26T00:01", False),   # 一，剛過午夜
])
def test_weekend_follows_taipei_not_utc(monkeypatch, iso, weekend):
    """台北清晨與深夜是 UTC 的前一天／後一天，判斷必須以台北為準。"""
    _at(monkeypatch, iso)
    assert clock.is_weekend() is weekend


def test_early_morning_schedule_maps_to_previous_utc_day():
    """台北 07:00 是前一天的 UTC 23:00——這正是位移的來源。"""
    assert clock.utc_time_for(7, 0) == time(23, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("taipei_hour,utc_hour", [
    (6, 22), (7, 23), (8, 0), (14, 6), (23, 15), (0, 16),
])
def test_utc_conversion(taipei_hour, utc_hour):
    assert clock.utc_time_for(taipei_hour).hour == utc_hour


def test_offset_is_fixed():
    """台北沒有日光節約時間；用固定 offset 是刻意的，不是偷懶。"""
    assert clock.TAIPEI.utcoffset(None).total_seconds() == 8 * 3600
