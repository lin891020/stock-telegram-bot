import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

_FILE = Path("data/alerts.json")

# ">1100" / "<950" / "+5%" / "-5%"
_PRICE_RE = re.compile(r"^([><])\s*(\d+(?:\.\d+)?)$")
_PCT_RE = re.compile(r"^([+-])\s*(\d+(?:\.\d+)?)\s*%$")


def parse_condition(text: str) -> Optional[dict]:
    """Parse an alert condition. Returns {kind, op, value} or None.

    kind "price": op ">" or "<", value = 價位門檻
    kind "pct":   op "+" or "-", value = 與前收盤比的漲/跌幅（%，正數）
    """
    text = text.strip()
    m = _PRICE_RE.match(text)
    if m:
        return {"kind": "price", "op": m.group(1), "value": float(m.group(2))}
    m = _PCT_RE.match(text)
    if m:
        return {"kind": "pct", "op": m.group(1), "value": float(m.group(2))}
    return None


def condition_text(alert: dict) -> str:
    """條件的機器可讀字串（可被 parse_condition 解析），例如 '>1100'、'+5%'。"""
    suffix = "%" if alert["kind"] == "pct" else ""
    return f"{alert['op']}{alert['value']:g}{suffix}"


def describe_condition(alert: dict) -> str:
    if alert["kind"] == "price":
        verb = "漲破" if alert["op"] == ">" else "跌破"
        return f"{verb} {alert['value']:g}"
    verb = "漲幅達" if alert["op"] == "+" else "跌幅達"
    return f"單日{verb} {alert['value']:g}%"


def is_triggered(alert: dict, price: float, prev_close: Optional[float]) -> bool:
    if alert["kind"] == "price":
        return price > alert["value"] if alert["op"] == ">" else price < alert["value"]
    if not prev_close:
        return False
    pct = (price - prev_close) / prev_close * 100
    return pct >= alert["value"] if alert["op"] == "+" else pct <= -alert["value"]


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


def get_alerts(user_id: int) -> list[dict]:
    return _load().get(str(user_id), [])


def add_alert(user_id: int, ticker: str, condition: dict) -> dict:
    """Add an alert and return it (with generated id)."""
    alert = {
        "id": uuid.uuid4().hex[:8],
        "ticker": ticker.upper(),
        "created": str(date.today()),
        **condition,
    }
    data = _load()
    data.setdefault(str(user_id), []).append(alert)
    _save(data)
    return alert


def remove_alert(user_id: int, alert_id: str) -> bool:
    data = _load()
    items = data.get(str(user_id), [])
    remaining = [a for a in items if a.get("id") != alert_id]
    if len(remaining) == len(items):
        return False
    data[str(user_id)] = remaining
    _save(data)
    return True


def all_alerts() -> dict[str, list[dict]]:
    """{user_id_str: [alerts]} for the check job."""
    return _load()
