import json
from pathlib import Path
from typing import Iterator

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


def iter_watchlists() -> Iterator[tuple[str, dict[str, str]]]:
    """逐一走訪所有使用者的自選股，回傳 (user_id_str, {ticker: name})。

    舊格式（list）的遷移只在 _migrate_user 一處處理。以前排程、推播、
    財報偵測各自寫一份 isinstance 判斷，格式一改就得改四個地方，
    漏掉的那個會靜默拿到空清單。
    """
    for user_id_str, raw in _load().items():
        items = _migrate_user(raw)
        if items:
            yield user_id_str, items


def all_tickers() -> list[str]:
    """所有使用者自選股的聯集，保留加入順序。"""
    seen: dict[str, None] = {}
    for _, items in iter_watchlists():
        for ticker in items:
            seen[ticker] = None
    return list(seen)


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
