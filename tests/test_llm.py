# tests/test_llm.py
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import bot.services.llm as llm_mod
from bot.services.llm import call_llm


@pytest.fixture(autouse=True)
def reset_client(monkeypatch):
    """client 是單例，測試之間要清掉，否則第二個測試會沿用前一個的 mock。"""
    monkeypatch.setattr(llm_mod, "_anthropic_client", None)


def _block(kind: str, **fields):
    return SimpleNamespace(type=kind, **fields)


def _response(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, model="test")


def _patched_call(response):
    with patch("bot.services.llm.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = response
        return call_llm("system", "user", model="claude-sonnet-4-6")


def test_call_llm_returns_text():
    assert _patched_call(_response(_block("text", text="這是分析報告"))) == "這是分析報告"


def test_skips_thinking_block():
    """啟用 thinking 的模型會把 thinking 排在第一個；直接取 content[0].text 會炸。"""
    response = _response(
        _block("thinking", thinking="讓我想想"),
        _block("text", text="結論"),
    )
    assert _patched_call(response) == "結論"


def test_joins_multiple_text_blocks():
    response = _response(_block("text", text="前半"), _block("text", text="後半"))
    assert _patched_call(response) == "前半後半"


def test_truncation_is_logged(caplog):
    response = _response(_block("text", text="斷在這"), stop_reason="max_tokens")
    with caplog.at_level("WARNING"):
        assert _patched_call(response) == "斷在這"
    assert "max_tokens" in caplog.text


def test_client_is_reused_across_calls():
    """每次呼叫重建 client 會連 httpx 連線池與 TLS 握手一起重來。"""
    with patch("bot.services.llm.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _response(
            _block("text", text="ok")
        )
        call_llm("system", "user", model="claude-sonnet-4-6")
        call_llm("system", "user", model="claude-sonnet-4-6")
    assert mock_cls.call_count == 1


# ── 模型端故障要跟資料故障分開 ────────────────────────────────────────
# 實測 Anthropic 信用額度用盡時，畫面只寫「分析失敗，請稍後再試」，
# 而那時再試一百次也一樣。

def test_provider_error_becomes_llm_unavailable(monkeypatch):
    import bot.services.llm as mod

    def boom(*a, **k):
        raise RuntimeError("Your credit balance is too low to access the Anthropic API")
    monkeypatch.setattr(mod, "_call_anthropic", boom)
    monkeypatch.setattr(mod, "_current_model", "claude-sonnet-5")

    with pytest.raises(mod.LLMUnavailable) as exc:
        mod.call_llm("sys", "user")
    assert exc.value.hint == "API 額度用盡，需要儲值"


def test_unknown_provider_error_still_wrapped(monkeypatch):
    import bot.services.llm as mod

    def boom(*a, **k):
        raise ValueError("something nobody has seen before")
    monkeypatch.setattr(mod, "_call_anthropic", boom)
    monkeypatch.setattr(mod, "_current_model", "claude-sonnet-5")

    with pytest.raises(mod.LLMUnavailable) as exc:
        mod.call_llm("sys", "user")
    assert exc.value.reason == "ValueError" and exc.value.hint == ""


def test_failure_text_tells_you_it_is_the_model():
    from bot.handlers.messaging import failure_text
    from bot.services.llm import LLMUnavailable

    text = failure_text(LLMUnavailable("BadRequestError", "API 額度用盡，需要儲值"))
    assert "AI 模型" in text and "儲值" in text
    assert "稍後再試" not in text, "額度用盡時叫人稍後再試是誤導"


def test_failure_text_keeps_the_old_wording_for_data_errors():
    from bot.handlers.messaging import failure_text
    assert failure_text(TimeoutError("yfinance 逾時")) == "❌ 分析失敗，請稍後再試"
