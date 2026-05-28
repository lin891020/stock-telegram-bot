# tests/test_llm.py
import pytest
from unittest.mock import patch, MagicMock
from bot.services.llm import call_llm

def _mock_anthropic_response(text: str):
    mock_content = MagicMock()
    mock_content.text = text
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]
    return mock_resp

def test_call_llm_anthropic_returns_string(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    import importlib, bot.services.llm as llm_mod
    importlib.reload(llm_mod)

    mock_create = MagicMock(return_value=_mock_anthropic_response("分析結果"))
    with patch.object(llm_mod.anthropic.Anthropic, "__init__", return_value=None), \
         patch("bot.services.llm.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create = mock_create
        result = llm_mod.call_llm("你是分析師", "分析台積電")

    assert isinstance(result, str)

def test_call_llm_returns_nonempty():
    mock_content = MagicMock()
    mock_content.text = "這是分析報告"
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]

    with patch("bot.services.llm.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_resp
        result = call_llm("system", "user")

    assert len(result) > 0
