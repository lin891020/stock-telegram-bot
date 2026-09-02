"""收盤速報要用**該市場當地**的日曆，不是台北的。

實測踩到的（2026-09-02 發現，上線一天）：美股收盤速報排在台北 05:30，
而台北的星期六清晨其實是紐約的星期五傍晚。用台北日曆判斷的話——

    星期五的美股收盤永遠不會推（台北那時是星期六，被當成週末跳過）
    星期一早上推的是星期五的資料，標題卻寫星期一的日期

數字全對、時間全錯，跟聯發科那次誤報同一個形狀。
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import bot.handlers.digest as digest
from bot.services import clock
from conftest import FakeContext

TP = ZoneInfo("Asia/Taipei")


def _at(monkeypatch, taipei_iso: str):
    """把「現在」固定成某個台北時刻，各市場自己換算當地時間。"""
    moment = datetime.fromisoformat(taipei_iso).replace(tzinfo=TP)
    monkeypatch.setattr(
        clock, "market_now",
        lambda market: moment.astimezone(clock.MARKET_TZ.get(market, clock.TAIPEI)),
    )


def _one_stock(monkeypatch, ticker, name, session: date):
    monkeypatch.setattr(digest, "iter_watchlists", lambda: iter([("1", {ticker: name})]))

    async def _quote(t):
        return {"name": name, "price": 220.0, "prev_close": 217.0, "market": "US"}
    monkeypatch.setattr(digest, "get_stock_summary", _quote)

    async def _session(t):
        return session
    monkeypatch.setattr(digest, "last_session_date", _session)


# ── 美股：台北的星期六是紐約的星期五 ──────────────────────────────────

@pytest.mark.asyncio
async def test_fridays_us_close_is_pushed_on_saturday_taipei(monkeypatch):
    """台北 08/29(六) 05:30 ＝ 紐約 08/28(五) 17:30，星期五剛收盤。"""
    _at(monkeypatch, "2026-08-29T05:30")
    assert clock.market_today("US") == date(2026, 8, 28)
    assert not clock.market_is_weekend("US"), "紐約還是星期五"

    _one_stock(monkeypatch, "NVDA", "NVIDIA", date(2026, 8, 28))
    ctx = FakeContext()
    await digest.send_closing_digest(ctx, "US")

    assert ctx.bot.sent, "星期五的美股收盤被當成週末跳過了"
    assert "2026/08/28" in ctx.bot.texts[0], "標題要寫那一場的日期，不是台北的今天"


@pytest.mark.asyncio
async def test_monday_morning_does_not_replay_fridays_close(monkeypatch):
    """台北 08/31(一) 05:30 ＝ 紐約 08/30(日)，週末沒有新的收盤。"""
    _at(monkeypatch, "2026-08-31T05:30")
    assert clock.market_today("US") == date(2026, 8, 30)
    assert clock.market_is_weekend("US")

    _one_stock(monkeypatch, "NVDA", "NVIDIA", date(2026, 8, 28))
    ctx = FakeContext()
    await digest.send_closing_digest(ctx, "US")
    assert ctx.bot.sent == [], "把星期五的收盤當成星期一的推出去了"


@pytest.mark.asyncio
async def test_us_holiday_is_skipped_without_a_holiday_table(monkeypatch):
    """感恩節是星期四——日曆擋不住，只有資料擋得住。

    最後一根日線停在前一天，就代表今天沒開。
    """
    _at(monkeypatch, "2026-11-27T05:30")          # 紐約 11/26 感恩節
    assert not clock.market_is_weekend("US"), "星期四不是週末，日曆擋不住"

    _one_stock(monkeypatch, "NVDA", "NVIDIA", date(2026, 11, 25))   # 最後一場是週三
    ctx = FakeContext()
    await digest.send_closing_digest(ctx, "US")
    assert ctx.bot.sent == [], "休市日把前一場的收盤當成今天的推出去了"


# ── 台股：當地日曆就是台北，行為不變 ──────────────────────────────────

@pytest.mark.asyncio
async def test_tw_still_uses_taipei(monkeypatch):
    _at(monkeypatch, "2026-09-02T14:00")
    assert clock.market_today("TW") == date(2026, 9, 2)

    monkeypatch.setattr(digest, "iter_watchlists", lambda: iter([("1", {"2330": "台積電"})]))

    async def _quote(t):
        return {"name": "台積電", "close": 2385.0, "prev_close": 2440.0,
                "market": "TW", "date": "2026/09/02"}
    monkeypatch.setattr(digest, "get_stock_summary", _quote)

    async def _session(t):
        return date(2026, 9, 2)
    monkeypatch.setattr(digest, "last_session_date", _session)

    ctx = FakeContext()
    await digest.send_closing_digest(ctx, "TW")
    assert ctx.bot.sent and "2026/09/02" in ctx.bot.texts[0]
    assert "（9/2 收盤）" not in ctx.bot.texts[0], "標題有日期了，逐行不該再掛一次"


@pytest.mark.asyncio
async def test_tw_holiday_is_skipped(monkeypatch):
    """颱風假／國定假日：TWSE 會回前一個交易日的收盤。"""
    _at(monkeypatch, "2026-09-02T14:00")
    monkeypatch.setattr(digest, "iter_watchlists", lambda: iter([("1", {"2330": "台積電"})]))

    async def _quote(t):
        return {"name": "台積電", "close": 2440.0, "prev_close": 2405.0,
                "market": "TW", "date": "2026/09/01"}
    monkeypatch.setattr(digest, "get_stock_summary", _quote)

    async def _session(t):
        return date(2026, 9, 1)
    monkeypatch.setattr(digest, "last_session_date", _session)

    ctx = FakeContext()
    await digest.send_closing_digest(ctx, "TW")
    assert ctx.bot.sent == []


# ── 預設時間必須在收盤之後 ────────────────────────────────────────────

def test_us_presets_are_all_after_the_us_close():
    """美股 16:00 ET ＝ 台北 04:00（夏令）／05:00（冬令）。

    22:00 台北是紐約 10:00——開盤後半小時，不是收盤。那個預設曾經在清單裡。
    """
    from bot.handlers.schedule import _JOBS

    for preset in _JOBS["us"].presets:
        hour = int(preset.split(":")[0])
        assert 4 <= hour <= 8, f"{preset} 不在美股收盤之後（台北 04:00–08:00）"


# ── 盤中速報 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_noon_snapshot_skipped_on_a_tw_holiday(monkeypatch):
    """颱風假／國定假日不推，否則會出現一整排 +0.00%。"""
    _at(monkeypatch, "2026-09-02T12:00")
    monkeypatch.setattr(digest, "iter_watchlists", lambda: iter([("1", {"2330": "台積電"})]))

    async def _session(t):
        return date(2026, 9, 1)          # 最後一場是昨天 → 今天沒開
    monkeypatch.setattr(digest, "last_session_date", _session)

    ctx = FakeContext()
    await digest.send_noon_snapshot(ctx)
    assert ctx.bot.sent == []


@pytest.mark.asyncio
async def test_noon_snapshot_uses_each_users_own_names(monkeypatch):
    """名稱要取自這個使用者的清單。

    以前是拿全域查表函式去找，多使用者時第一個人取的名字會出現在第二個人
    的推播裡——跟最近查詢紀錄當初是全域共用的同一種錯。
    """
    _at(monkeypatch, "2026-09-02T12:00")
    monkeypatch.setattr(digest, "iter_watchlists", lambda: iter([
        ("1", {"2330": "台積電"}),
        ("2", {"2330": "我的定存股"}),
    ]))

    async def _session(t):
        return date(2026, 9, 2)
    monkeypatch.setattr(digest, "last_session_date", _session)

    async def _quote(t):
        return 2385.0, 2440.0
    monkeypatch.setattr(digest, "intraday_quote", _quote)

    ctx = FakeContext()
    await digest.send_noon_snapshot(ctx)

    assert len(ctx.bot.sent) == 2
    assert "台積電(2330)" in ctx.bot.texts[0]
    assert "我的定存股(2330)" in ctx.bot.texts[1]
    assert "台積電" not in ctx.bot.texts[1], "把別人的名稱推給第二個使用者了"
