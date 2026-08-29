"""每日巡檢的測試。

跟錯誤處理同一類：只在別的東西壞掉時才需要它。如果它自己壞了，
你不會發現——因為它正常運作時的表現就是「安靜」，跟壞掉一模一樣。
"""
import pytest

import bot.handlers.health as health_mod
from conftest import FakeBot, FakeContext


def _stub(monkeypatch, results):
    async def _run():
        return results
    monkeypatch.setattr(health_mod, "run_checks", _run)


@pytest.mark.asyncio
async def test_stays_quiet_when_everything_is_green(monkeypatch):
    _stub(monkeypatch, [("yfinance", True, "AAPL $319"), ("TWSE", True, "1377 檔")])
    ctx = FakeContext()
    await health_mod.health_watchdog(ctx)
    assert ctx.bot.sent == [], "全綠還推播的話，你很快就會學會忽略它"


@pytest.mark.asyncio
async def test_reports_only_the_failures(monkeypatch):
    _stub(monkeypatch, [
        ("yfinance", True, "AAPL $319"),
        ("lxml 解析器", False, "未安裝"),
        ("PDF 中文字型", False, "缺字型"),
    ])
    ctx = FakeContext()
    await health_mod.health_watchdog(ctx)

    assert len(ctx.bot.sent) == 1
    body = ctx.bot.texts[0]
    assert "2 項異常" in body
    assert "lxml 解析器" in body and "PDF 中文字型" in body
    assert "yfinance" not in body, "正常的項目不該混進警告裡"


@pytest.mark.asyncio
async def test_a_crashing_check_counts_as_a_failure(monkeypatch):
    """單一檢查拋例外時要算成紅燈，不能讓整個巡檢靜靜跳過。"""
    def _boom():
        raise RuntimeError("網路斷了")
    monkeypatch.setattr(health_mod, "_CHECKS", [("SEC EDGAR", _boom)])

    ctx = FakeContext()
    await health_mod.health_watchdog(ctx)

    assert len(ctx.bot.sent) == 1
    assert "SEC EDGAR" in ctx.bot.texts[0]
    assert "RuntimeError" in ctx.bot.texts[0]


@pytest.mark.asyncio
async def test_watchdog_never_raises(monkeypatch):
    """巡檢自己爆掉不能把 JobQueue 拖下水。"""
    async def _boom():
        raise RuntimeError("巡檢自己壞了")
    monkeypatch.setattr(health_mod, "run_checks", _boom)

    await health_mod.health_watchdog(FakeContext())   # 不可拋出


@pytest.mark.asyncio
async def test_send_failure_does_not_raise(monkeypatch):
    _stub(monkeypatch, [("lxml", False, "未安裝")])
    await health_mod.health_watchdog(FakeContext(bot=FakeBot(fail_on={0})))
