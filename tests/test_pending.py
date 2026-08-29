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
    ctx.user_data["pending"] = {"action": "price", "expires": time.time() + 60}
    p = pop_pending(ctx)
    assert p["action"] == "price"
    # 單發：取出後即清除
    assert pop_pending(ctx) is None


def test_pop_pending_expired():
    ctx = FakeContext()
    ctx.user_data["pending"] = {"action": "price", "expires": time.time() - 1}
    assert pop_pending(ctx) is None


def test_pending_extra_fields_preserved():
    ctx = FakeContext()
    ctx.user_data["pending"] = {
        "action": "alert", "ticker": "2330", "expires": time.time() + 60,
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
    ctx.user_data["pending"] = {"action": "dummy", "expires": time.time() + 60}
    handled = await dispatch_pending("fake-update", ctx)
    assert handled is True
    assert calls == [("fake-update", "dummy")]


@pytest.mark.asyncio
async def test_dispatch_pending_no_pending():
    assert await dispatch_pending("fake-update", FakeContext()) is False


def test_expiry_uses_wall_clock_not_monotonic():
    """user_data 會被 PicklePersistence 寫到磁碟並跨重啟讀回。

    monotonic 是「行程啟動以來的秒數」，重啟後基準歸零——舊行程存的值
    拿到新行程比對會完全錯亂。用 time.time() 才能安全持久化。
    """
    ctx = FakeContext()
    # 用 wall clock 記的未來時間必須被視為有效
    ctx.user_data["pending"] = {"action": "price", "expires": time.time() + 60}
    assert pop_pending(ctx) is not None

    # monotonic 記的值（數量級遠小於 epoch）必須被視為過期，而不是誤判成有效
    ctx.user_data["pending"] = {"action": "price", "expires": time.monotonic() + 60}
    assert pop_pending(ctx) is None


def test_clear_pending():
    from bot.handlers.pending import clear_pending
    ctx = FakeContext()
    assert clear_pending(ctx) is False          # 沒東西可清
    ctx.user_data["pending"] = {"action": "price", "expires": time.time() + 60}
    assert clear_pending(ctx) is True
    assert pop_pending(ctx) is None
