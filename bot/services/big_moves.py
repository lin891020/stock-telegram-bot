"""自選股異常波動偵測：台股漲停／跌停、美股單日 ±10%。

台股漲跌停不是「剛好 ±10%」——限價要照檔位（tick）向內取整，
例如前收 1090 的漲停是 1195（不是 1199），所以直接比 10% 會漏掉。
這裡把限價算出來比對，避免用「漲超過 9.5% 就當漲停」這種近似值。

推播去重：同一天、同一支、同一個方向只推一次；換日自動清空。
"""
import json
import math
from datetime import date
from pathlib import Path
from typing import Optional

from bot.services.stock import is_taiwan_stock

_FILE = Path("data/big_moves.json")

US_PCT_THRESHOLD = 10.0  # 美股單日漲跌幅門檻（%）

# 台股股票檔位：(價格上限, 檔位)，價格 >= 1000 用最後一檔
_TW_TICKS = [(10, 0.01), (50, 0.05), (100, 0.1), (500, 0.5), (1000, 1.0)]
_TW_TICK_ABOVE = 5.0

_PRICE_EPSILON = 1e-6


def tw_tick(price: float) -> float:
    """該價位適用的最小升降單位。"""
    for upper, tick in _TW_TICKS:
        if price < upper:
            return tick
    return _TW_TICK_ABOVE


def tw_limit_prices(prev_close: float) -> tuple[float, float]:
    """(漲停價, 跌停價)：±10% 後照檔位往內取整。"""
    raw_up = prev_close * 1.1
    raw_down = prev_close * 0.9
    up_tick = tw_tick(raw_up)
    down_tick = tw_tick(raw_down)
    limit_up = math.floor(raw_up / up_tick + _PRICE_EPSILON) * up_tick
    limit_down = math.ceil(raw_down / down_tick - _PRICE_EPSILON) * down_tick
    return round(limit_up, 2), round(limit_down, 2)


def classify_move(ticker: str, price: Optional[float], prev_close: Optional[float]) -> Optional[dict]:
    """回傳 {direction, pct, headline} 或 None（未達門檻／資料不足）。"""
    if not price or not prev_close:
        return None

    pct = (price - prev_close) / prev_close * 100

    if is_taiwan_stock(ticker):
        limit_up, limit_down = tw_limit_prices(prev_close)
        if price >= limit_up - _PRICE_EPSILON:
            return {"direction": "up", "pct": pct, "headline": "漲停"}
        if price <= limit_down + _PRICE_EPSILON:
            return {"direction": "down", "pct": pct, "headline": "跌停"}
        return None

    if pct >= US_PCT_THRESHOLD:
        return {"direction": "up", "pct": pct, "headline": f"單日大漲（超過 {US_PCT_THRESHOLD:g}%）"}
    if pct <= -US_PCT_THRESHOLD:
        return {"direction": "down", "pct": pct, "headline": f"單日大跌（超過 {US_PCT_THRESHOLD:g}%）"}
    return None


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


def _today_state() -> dict:
    """今天的推播記錄；跨日直接視為空的（下次 mark_sent 才寫回）。"""
    data = _load()
    if data.get("date") != str(date.today()):
        return {"date": str(date.today()), "sent": []}
    return data


def _key(user_id, ticker: str, direction: str) -> str:
    return f"{user_id}:{ticker}:{direction}"


def was_sent(user_id, ticker: str, direction: str) -> bool:
    return _key(user_id, ticker, direction) in _today_state()["sent"]


def mark_sent(user_id, ticker: str, direction: str) -> None:
    state = _today_state()
    key = _key(user_id, ticker, direction)
    if key not in state["sent"]:
        state["sent"].append(key)
    _save(state)
