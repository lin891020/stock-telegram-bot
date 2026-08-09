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
