"""到價提醒的順序測試——鎖住「先送成功才移除」這個對的行為。

財報那條當初就是把順序寫反了（先推進基準才產生報告），一次失敗
那季就永遠遺失。提醒這條本來是對的，但沒有任何東西擋著它被改壞。
"""
import pytest

import bot.handlers.alert as alert_mod
from conftest import FakeBot, FakeContext


@pytest.fixture
def wiring(monkeypatch):
    state = {"removed": []}
    alert = {"id": "abc123", "ticker": "2330", "kind": "price", "op": ">", "value": 1000.0}

    monkeypatch.setattr(alert_mod, "all_alerts", lambda: {"123456789": [alert]})
    monkeypatch.setattr(alert_mod, "_tw_market_open", lambda now: True)
    monkeypatch.setattr(alert_mod, "_us_market_open", lambda now: True)
    monkeypatch.setattr(
        alert_mod, "remove_alert",
        lambda uid, aid: state["removed"].append((uid, aid)),
    )
    monkeypatch.setattr(alert_mod, "_fetch_quote_sync", lambda t: (1100.0, 1050.0))
    return state


@pytest.mark.asyncio
async def test_removes_alert_after_successful_push(wiring):
    ctx = FakeContext()
    await alert_mod.check_alerts(ctx)

    assert len(ctx.bot.sent) == 1
    assert wiring["removed"] == [(123456789, "abc123")]


@pytest.mark.asyncio
async def test_keeps_alert_when_push_fails(wiring):
    """傳送失敗時提醒要留著，下一輪才能再試。

    反過來的話你會永遠錯過那次到價，而且完全不知道發生過。
    """
    ctx = FakeContext(bot=FakeBot(fail_on={0}))
    await alert_mod.check_alerts(ctx)

    assert wiring["removed"] == [], "傳送失敗卻把提醒刪了 → 這次到價永遠遺失"


@pytest.mark.asyncio
async def test_untriggered_alert_is_left_alone(monkeypatch, wiring):
    monkeypatch.setattr(alert_mod, "_fetch_quote_sync", lambda t: (900.0, 890.0))
    ctx = FakeContext()
    await alert_mod.check_alerts(ctx)

    assert ctx.bot.sent == []
    assert wiring["removed"] == []


@pytest.mark.asyncio
async def test_missing_quote_does_not_trigger(monkeypatch, wiring):
    """抓不到報價時不能當成觸發——不然資料源一抖動就狂噴通知。"""
    monkeypatch.setattr(alert_mod, "_fetch_quote_sync", lambda t: (None, None))
    ctx = FakeContext()
    await alert_mod.check_alerts(ctx)

    assert ctx.bot.sent == []
    assert wiring["removed"] == []
