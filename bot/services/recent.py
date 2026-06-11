import json
from pathlib import Path

_FILE = Path("data/recent.json")
_MAX = 5


def _load() -> list:
    if not _FILE.exists():
        return []
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def add_recent(ticker: str, name: str = "") -> None:
    """記錄最近查過的股票（最新在前，去重，最多 5 筆）。"""
    items = [i for i in _load() if i.get("ticker") != ticker]
    items.insert(0, {"ticker": ticker, "name": name or ticker})
    _FILE.parent.mkdir(exist_ok=True)
    _FILE.write_text(
        json.dumps(items[:_MAX], ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_recent() -> list[dict]:
    """[{ticker, name}] 最新在前。"""
    return _load()
