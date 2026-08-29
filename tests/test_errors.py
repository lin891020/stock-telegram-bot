"""全域錯誤處理本身的測試。

這段程式只在別的東西壞掉時才會執行——如果它自己有 bug，
失效的時機正好是最需要它的時候，而且不會有任何徵兆。
"""
import pytest

import bot.handlers.errors as errors_mod
from conftest import FakeBot, FakeContext


class FakeUser:
    id = 123456789


class FakeChat:
    id = 123456789


def _update(text=None, callback_data=None):
    """做一個夠像 telegram.Update 的物件（isinstance 檢查要過）。"""
    from telegram import Update
    upd = Update.__new__(Update)
    msg = type("M", (), {"text": text})() if text else None
    cbq = type("C", (), {"data": callback_data})() if callback_data else None
    object.__setattr__(upd, "_frozen", False)
    upd.message = msg
    upd.callback_query = cbq
    upd._effective_chat = FakeChat()
    return upd


@pytest.mark.asyncio
async def test_reports_error_to_the_user(monkeypatch):
    monkeypatch.setattr(errors_mod.Update, "effective_chat", property(lambda s: FakeChat()))
    ctx = FakeContext()
    ctx.error = ValueError("查無此股票")

    await errors_mod.error_handler(_update(text="/price XYZ"), ctx)

    assert len(ctx.bot.sent) == 1
    body = ctx.bot.texts[0]
    assert "ValueError" in body and "查無此股票" in body
    assert "/health" in body, "錯誤訊息應該給使用者下一步可以做什麼"


@pytest.mark.asyncio
async def test_names_what_the_user_was_doing(monkeypatch):
    monkeypatch.setattr(errors_mod.Update, "effective_chat", property(lambda s: FakeChat()))
    ctx = FakeContext()
    ctx.error = RuntimeError("boom")

    await errors_mod.error_handler(_update(callback_data="erpt_NVDA"), ctx)
    assert "erpt_NVDA" in ctx.bot.texts[0]


@pytest.mark.asyncio
async def test_job_errors_still_reach_you():
    """JobQueue 的例外沒有 update，但排程壞掉更需要你知道。"""
    ctx = FakeContext()
    ctx.error = RuntimeError("排程炸了")

    await errors_mod.error_handler(None, ctx)

    assert len(ctx.bot.sent) == 1
    assert ctx.bot.sent[0]["chat_id"] == errors_mod.ALLOWED_TELEGRAM_ID


@pytest.mark.asyncio
async def test_does_not_raise_when_notification_itself_fails():
    """連錯誤通知都送不出去時只能記 log，再往上拋會變成無窮迴圈。"""
    ctx = FakeContext(bot=FakeBot(fail_on={0}))
    ctx.error = RuntimeError("原始錯誤")

    await errors_mod.error_handler(None, ctx)   # 不可拋出


@pytest.mark.asyncio
async def test_long_traceback_is_trimmed():
    """Telegram 單則上限 4096 字元，超過整則會送不出去。"""
    ctx = FakeContext()
    try:
        raise RuntimeError("x" * 9000)
    except RuntimeError as e:
        ctx.error = e

    await errors_mod.error_handler(None, ctx)
    assert len(ctx.bot.texts[0]) < 4096


@pytest.mark.asyncio
async def test_stays_under_limit_with_escape_heavy_traceback():
    """traceback 裡滿是 <module>、<lambda>，跳脫後長度會膨脹。

    先截斷再跳脫的話長度會失準：實測 2500 字元膨脹到 3660，整則
    超過 Telegram 的 4096 上限而送不出去——錯誤通知在最需要它的
    時候消失，而且只留下一行 log。
    """
    ctx = FakeContext()
    try:
        exec(compile("\n" * 200 + "raise RuntimeError('<boom> & <bang>' * 400)", "<string>", "exec"))
    except RuntimeError as e:
        ctx.error = e

    await errors_mod.error_handler(None, ctx)

    assert len(ctx.bot.sent) == 1, "訊息根本沒送出去"
    assert len(ctx.bot.texts[0]) <= 4096
    assert ctx.bot.texts[0].count("<pre>") == ctx.bot.texts[0].count("</pre>"), "HTML 標籤被截斷"
