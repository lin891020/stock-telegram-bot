import json
import re
from pathlib import Path
from typing import Optional

_FILE = Path("data/settings.json")

# Schedule keys → (settings.json field, default Taipei time)
# 美股收盤已併入起床報（news），不再獨立排程
TIME_KEYS: dict[str, tuple[str, str]] = {
    "news": ("daily_news_time", "06:30"),
    "tw_close": ("tw_close_time", "14:00"),
}

DEFAULT_NEWS_TIME = TIME_KEYS["news"][1]

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(text: str) -> Optional[tuple[int, int]]:
    """Parse 'HH:MM' (24h). Returns (hour, minute) or None if invalid."""
    m = _TIME_RE.match(text.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _load() -> dict:
    if not _FILE.exists():
        return {}
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _FILE.parent.mkdir(exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_time(key: str) -> str:
    """Scheduled push time as 'HH:MM' Taipei. key: news / tw_close / us_close."""
    field, default = TIME_KEYS[key]
    value = _load().get(field, default)
    return value if parse_hhmm(value) else default


def set_time(key: str, hhmm: str) -> str:
    """Validate and persist a push time. Returns the normalized 'HH:MM'."""
    field, _ = TIME_KEYS[key]
    parsed = parse_hhmm(hhmm)
    if parsed is None:
        raise ValueError(f"Invalid time: {hhmm}")
    normalized = f"{parsed[0]:02d}:{parsed[1]:02d}"
    data = _load()
    data[field] = normalized
    _save(data)
    return normalized


def get_news_time() -> str:
    """Daily morning-news time as 'HH:MM' in Taipei time."""
    return get_time("news")


def set_news_time(hhmm: str) -> str:
    """Validate and persist the morning-news time. Returns the normalized 'HH:MM'."""
    return set_time("news", hhmm)


def get_saved_model() -> Optional[str]:
    """Last model key selected via /model, or None if never set."""
    return _load().get("current_model")


def save_model(model_key: str) -> None:
    data = _load()
    data["current_model"] = model_key
    _save(data)
