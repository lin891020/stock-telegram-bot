# tests/test_github_store.py
import pytest
import json
import base64
from unittest.mock import patch, MagicMock
from bot.services.github_store import read_profile, write_profile

def _make_github_response(data: dict) -> MagicMock:
    """Helper: mock a GitHub API GET response with encoded JSON."""
    content = base64.b64encode(json.dumps(data).encode()).decode()
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"content": content + "\n", "sha": "abc123"}
    mock.raise_for_status = MagicMock()
    return mock

def test_read_profile_returns_dict():
    profile = {"monthly_income": 50000, "goal": "緊急備用金"}
    with patch("bot.services.github_store.requests.get", return_value=_make_github_response(profile)):
        result = read_profile()
    assert result["monthly_income"] == 50000
    assert result["goal"] == "緊急備用金"

def test_read_profile_returns_empty_on_404():
    mock = MagicMock()
    mock.status_code = 404
    with patch("bot.services.github_store.requests.get", return_value=mock):
        result = read_profile()
    assert result == {}

def test_write_profile_calls_put():
    get_mock = _make_github_response({})
    put_mock = MagicMock()
    put_mock.raise_for_status = MagicMock()

    with patch("bot.services.github_store.requests.get", return_value=get_mock), \
         patch("bot.services.github_store.requests.put", return_value=put_mock) as mock_put:
        write_profile({"monthly_income": 60000})

    mock_put.assert_called_once()
    call_json = mock_put.call_args[1]["json"]
    assert call_json["sha"] == "abc123"
    decoded = json.loads(base64.b64decode(call_json["content"]).decode())
    assert decoded["monthly_income"] == 60000
