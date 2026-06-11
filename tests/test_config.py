import pytest
import os

def test_config_loads_required_vars(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("ALLOWED_TELEGRAM_ID", "999")
    import importlib
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.TELEGRAM_BOT_TOKEN == "abc123"
    assert cfg.ALLOWED_TELEGRAM_ID == 999

def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Prevent load_dotenv from re-reading the token from a local .env file
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    import importlib
    import bot.config as cfg
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        importlib.reload(cfg)
