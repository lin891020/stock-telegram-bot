"""最近查詢紀錄要分使用者。

以前是全域共用一個 list。單使用者情境下不會出事，但那是湊巧安全的：
多加一個 Telegram ID，第二個人就會在自己的 /start 主選單上看到
第一個人查過哪些股票，而且沒有任何徵兆。
"""
import json

from bot.services.recent import _MAX, add_recent, get_recent


def test_users_do_not_see_each_other(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.services.recent._FILE", tmp_path / "recent.json")
    add_recent(111, "2330", "台積電")
    add_recent(222, "NVDA", "NVIDIA")

    assert [i["ticker"] for i in get_recent(111)] == ["2330"]
    assert [i["ticker"] for i in get_recent(222)] == ["NVDA"]


def test_newest_first_and_deduped(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.services.recent._FILE", tmp_path / "recent.json")
    for t in ("2330", "NVDA", "2330"):
        add_recent(111, t)
    assert [i["ticker"] for i in get_recent(111)] == ["2330", "NVDA"]


def test_capped(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.services.recent._FILE", tmp_path / "recent.json")
    for i in range(_MAX + 3):
        add_recent(111, f"T{i}")
    assert len(get_recent(111)) == _MAX


def test_unknown_user_gets_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.services.recent._FILE", tmp_path / "recent.json")
    add_recent(111, "2330")
    assert get_recent(999) == []


def test_old_global_list_is_not_shown_to_anyone(tmp_path, monkeypatch):
    """升級時既有的全域 list 不該突然變成某個人的紀錄。"""
    path = tmp_path / "recent.json"
    path.write_text(json.dumps([{"ticker": "2330", "name": "台積電"}]))
    monkeypatch.setattr("bot.services.recent._FILE", path)

    assert get_recent(111) == []
    add_recent(111, "NVDA")
    assert [i["ticker"] for i in get_recent(111)] == ["NVDA"]
