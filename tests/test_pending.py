import time

import pytest

import bot.handlers.pending as pending
from bot.handlers.pending import register, pop_pending, dispatch_pending, PENDING_HANDLERS


class FakeContext:
    def __init__(self):
        self.user_data = {}


def test_pop_pending_empty():
    assert pop_pending(FakeContext()) is None


def test_pop_pending_valid_and_consumed():
    ctx = FakeContext()
    ctx.user_data["pending"] = {"action": "price", "expires": time.monotonic() + 60}
    p = pop_pending(ctx)
    assert p["action"] == "price"
    # 單發：取出後即清除
    assert pop_pending(ctx) is None


def test_pop_pending_expired():
    ctx = FakeContext()
    ctx.user_data["pending"] = {"action": "price", "expires": time.monotonic() - 1}
    assert pop_pending(ctx) is None


def test_pending_extra_fields_preserved():
    ctx = FakeContext()
    ctx.user_data["pending"] = {
        "action": "alert", "ticker": "2330", "expires": time.monotonic() + 60,
    }
    assert pop_pending(ctx)["ticker"] == "2330"


@pytest.mark.asyncio
async def test_dispatch_pending_routes_to_handler(monkeypatch):
    monkeypatch.setattr(pending, "PENDING_HANDLERS", {})
    calls = []

    @register("dummy")
    async def _dummy(update, context, p):
        calls.append((update, p["action"]))

    ctx = FakeContext()
    ctx.user_data["pending"] = {"action": "dummy", "expires": time.monotonic() + 60}
    handled = await dispatch_pending("fake-update", ctx)
    assert handled is True
    assert calls == [("fake-update", "dummy")]


@pytest.mark.asyncio
async def test_dispatch_pending_no_pending():
    assert await dispatch_pending("fake-update", FakeContext()) is False
