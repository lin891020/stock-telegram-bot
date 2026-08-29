"""財報推播 job 的「順序」測試。

今天修的 BUG 1 就在這裡：偵測、產生報告、推播、推進基準四件事的先後。
services 層的 commit_event 有測，但「handler 有沒有在正確的時機呼叫它」
一直沒有任何東西擋著——而那正是出錯的地方。
"""
import pytest

import bot.handlers.earnings as earnings_mod
from conftest import FakeBot, FakeContext


@pytest.fixture
def wiring(monkeypatch):
    """把 job 的外部相依全部換掉，只留下順序邏輯。"""
    state = {"committed": [], "briefs": 0}

    monkeypatch.setattr(earnings_mod, "all_watchlist_tickers", lambda: ["NVDA"])
    monkeypatch.setattr(earnings_mod, "prune_state", lambda tickers: None)
    monkeypatch.setattr(
        earnings_mod, "commit_event",
        lambda ticker, date: state["committed"].append((ticker, date)),
    )

    async def _event(ticker):
        return {"date": "2026-08-26", "signal": "SEC 申報"}
    monkeypatch.setattr(earnings_mod, "detect_earnings_event", _event)

    class _Evidence:
        missing = []

    async def _brief(ticker):
        state["briefs"] += 1
        return "營收：...", _Evidence(), "NVIDIA(NVDA)"
    monkeypatch.setattr(earnings_mod, "build_brief", _brief)

    return state


@pytest.mark.asyncio
async def test_commits_after_successful_push(wiring):
    ctx = FakeContext()
    await earnings_mod.poll_earnings_announcements(ctx)

    assert len(ctx.bot.sent) == 1
    assert "NVIDIA(NVDA)" in ctx.bot.texts[0]
    assert wiring["committed"] == [("NVDA", "2026-08-26")]


@pytest.mark.asyncio
async def test_does_not_commit_when_report_generation_fails(monkeypatch, wiring):
    """報告產生失敗（LLM 逾時、SEC 限流）時基準不可以往前推。

    推了的話下一輪偵測就回 None，那一季的財報永遠不會再送達——
    而且完全沒有徵兆，因為例外被 catch 掉只寫進 log。
    """
    async def _boom(ticker):
        raise RuntimeError("LLM 逾時")
    monkeypatch.setattr(earnings_mod, "build_brief", _boom)

    ctx = FakeContext()
    await earnings_mod.poll_earnings_announcements(ctx)

    assert ctx.bot.sent == []
    assert wiring["committed"] == [], "報告失敗卻推進了基準 → 這季永遠遺失"


@pytest.mark.asyncio
async def test_does_not_commit_when_send_fails(wiring):
    """訊息真的送不出去時也不能推進基準。"""
    ctx = FakeContext(bot=FakeBot(fail_on={0}))
    await earnings_mod.poll_earnings_announcements(ctx)

    assert wiring["committed"] == [], "傳送失敗卻推進了基準"


@pytest.mark.asyncio
async def test_one_ticker_failing_does_not_stop_the_rest(monkeypatch, wiring):
    """一支掛掉不能拖累其他支——財報季是好幾支擠在同幾天。"""
    monkeypatch.setattr(earnings_mod, "all_watchlist_tickers", lambda: ["NVDA", "AAPL"])

    async def _brief(ticker):
        if ticker == "NVDA":
            raise RuntimeError("SEC 限流")
        return "營收：...", type("E", (), {"missing": []})(), "Apple(AAPL)"
    monkeypatch.setattr(earnings_mod, "build_brief", _brief)

    ctx = FakeContext()
    await earnings_mod.poll_earnings_announcements(ctx)

    assert [t for t, _ in wiring["committed"]] == ["AAPL"]
    assert len(ctx.bot.sent) == 1


@pytest.mark.asyncio
async def test_no_event_means_no_push_and_no_commit(monkeypatch, wiring):
    async def _none(ticker):
        return None
    monkeypatch.setattr(earnings_mod, "detect_earnings_event", _none)

    ctx = FakeContext()
    await earnings_mod.poll_earnings_announcements(ctx)

    assert ctx.bot.sent == []
    assert wiring["committed"] == []
    assert wiring["briefs"] == 0, "沒有事件卻還是跑了 LLM"
