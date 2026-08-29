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


def test_requirements_declares_the_extras_the_code_imports():
    """main.py 用了 AIORateLimiter，它需要 rate-limiter extra。

    少了 extra 的話 bot 在啟動時就 RuntimeError——而單元測試不會發現，
    因為測試不會真的組 Application。
    """
    from pathlib import Path
    reqs = Path(__file__).resolve().parents[1] / "requirements.txt"
    line = next(
        l for l in reqs.read_text(encoding="utf-8").splitlines()
        if l.startswith("python-telegram-bot")
    )
    assert "rate-limiter" in line, "main.py 用 AIORateLimiter，requirements 卻沒宣告 extra"
    assert "job-queue" in line, "所有排程都靠 job-queue extra"
