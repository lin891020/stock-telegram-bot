"""最近查過的股票，用在 /start 的快捷按鈕。

依使用者分開存。目前 auth 只放行一個 Telegram ID，所以現在不會有人
看到別人的紀錄——但那是「湊巧安全」：哪天多加一個 ID，第二個人會直接
在自己的主選單上看到第一個人查過什麼，而且沒有任何徵兆。
格式與 watchlist.json 一致（{user_id: ...}），遷移只在 _migrate 一處處理。
"""
from pathlib import Path

from bot.services.store import load_json, save_json

_FILE = Path("data/recent.json")
_MAX = 5


def _migrate(raw) -> dict:
    """舊格式是全域共用的一個 list，直接丟棄。

    無法知道那些紀錄是誰查的，掛到任何人底下都是猜的；留著又沒人讀得到，
    只是一筆永遠不會被用到的死資料。代價是升級當下主選單少三顆快捷按鈕，
    查一次就回來了。
    """
    return raw if isinstance(raw, dict) else {}


def _load() -> dict:
    return _migrate(load_json(_FILE, {}))


def add_recent(user_id: int, ticker: str, name: str = "") -> None:
    """記錄最近查過的股票（最新在前，去重，最多 5 筆）。"""
    data = _load()
    key = str(user_id)
    items = [i for i in data.get(key, []) if i.get("ticker") != ticker]
    items.insert(0, {"ticker": ticker, "name": name or ticker})
    data[key] = items[:_MAX]
    save_json(_FILE, data)


def get_recent(user_id: int) -> list[dict]:
    """[{ticker, name}] 最新在前。只回這個使用者自己的。"""
    return _load().get(str(user_id), [])
