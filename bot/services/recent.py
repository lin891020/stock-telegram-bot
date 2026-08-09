from pathlib import Path

from bot.services.store import load_json, save_json

_FILE = Path("data/recent.json")
_MAX = 5


def _load() -> list:
    return load_json(_FILE, [])


def add_recent(ticker: str, name: str = "") -> None:
    """記錄最近查過的股票（最新在前，去重，最多 5 筆）。"""
    items = [i for i in _load() if i.get("ticker") != ticker]
    items.insert(0, {"ticker": ticker, "name": name or ticker})
    save_json(_FILE, items[:_MAX])


def get_recent() -> list[dict]:
    """[{ticker, name}] 最新在前。"""
    return _load()
