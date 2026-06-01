import re
import httpx
import logging

logger = logging.getLogger(__name__)

_TWSE_API = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
_cache: dict[str, str] = {}  # {code: name}


def load_tw_stock_list() -> None:
    """Fetch all TWSE listed stocks and cache {code: name}. Call once on startup."""
    global _cache
    try:
        resp = httpx.get(_TWSE_API, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        _cache = {
            item["Code"]: item["Name"]
            for item in data
            if item.get("Code") and item.get("Name")
        }
        logger.info("Loaded %d TW stocks into cache", len(_cache))
    except Exception as e:
        logger.warning("Failed to load TW stock list: %s", e)


def get_tw_name(code: str) -> str | None:
    """Return company name for a TW stock code, or None if not in cache."""
    return _cache.get(code.upper())


def has_chinese(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text))


def search_tw_stocks(query: str, max_results: int = 5) -> list[dict]:
    """Search TW stocks by name substring. Returns list of {symbol, name}."""
    if not _cache:
        return []
    results = []
    for code, name in _cache.items():
        if query in name:
            results.append({"symbol": code, "name": name})
        if len(results) >= max_results:
            break
    return results
