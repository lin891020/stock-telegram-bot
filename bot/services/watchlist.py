import json
from pathlib import Path

_FILE = Path("data/watchlist.json")


def _load() -> dict:
    if not _FILE.exists():
        return {}
    return json.loads(_FILE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    _FILE.parent.mkdir(exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _migrate_user(raw) -> dict:
    """Convert old list format ["TICKER"] to new dict {"TICKER": "TICKER"}."""
    if isinstance(raw, list):
        return {t: t for t in raw}
    return raw if isinstance(raw, dict) else {}


def get_watchlist(user_id: int) -> list[str]:
    """Return list of ticker symbols."""
    return list(_migrate_user(_load().get(str(user_id), {})).keys())


def get_watchlist_with_names(user_id: int) -> list[dict]:
    """Return list of {ticker, name} dicts."""
    items = _migrate_user(_load().get(str(user_id), {}))
    return [{"ticker": t, "name": n} for t, n in items.items()]


def add_ticker(user_id: int, ticker: str, name: str = "") -> bool:
    data = _load()
    key = str(user_id)
    items = _migrate_user(data.get(key, {}))
    if ticker in items:
        return False
    items[ticker] = name or ticker
    data[key] = items
    _save(data)
    return True


def remove_ticker(user_id: int, ticker: str) -> bool:
    data = _load()
    key = str(user_id)
    items = _migrate_user(data.get(key, {}))
    if ticker not in items:
        return False
    del items[ticker]
    data[key] = items
    _save(data)
    return True
