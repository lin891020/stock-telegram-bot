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


def get_watchlist(user_id: int) -> list[str]:
    return _load().get(str(user_id), [])


def add_ticker(user_id: int, ticker: str) -> bool:
    data = _load()
    key = str(user_id)
    tickers = data.get(key, [])
    if ticker in tickers:
        return False
    tickers.append(ticker)
    data[key] = tickers
    _save(data)
    return True


def remove_ticker(user_id: int, ticker: str) -> bool:
    data = _load()
    key = str(user_id)
    tickers = data.get(key, [])
    if ticker not in tickers:
        return False
    tickers.remove(ticker)
    data[key] = tickers
    _save(data)
    return True
