import json
import os

import pytest

from bot.services.store import load_json, save_json


def test_roundtrip(tmp_path):
    path = tmp_path / "x.json"
    save_json(path, {"a": 1, "中文": "值"})
    assert load_json(path, {}) == {"a": 1, "中文": "值"}


def test_missing_file_returns_default(tmp_path):
    assert load_json(tmp_path / "nope.json", {}) == {}
    assert load_json(tmp_path / "nope.json", []) == []


def test_corrupt_file_returns_default_instead_of_raising(tmp_path):
    """半截檔案不該讓整隻 bot 掛掉——自選股幾乎每個指令都要讀。"""
    path = tmp_path / "x.json"
    path.write_text('{"a": 1, "b"', encoding="utf-8")
    assert load_json(path, {}) == {}


def test_creates_parent_directory(tmp_path):
    path = tmp_path / "deep" / "nested" / "x.json"
    save_json(path, {"ok": True})
    assert load_json(path, {}) == {"ok": True}


def test_no_tmp_files_left_behind(tmp_path):
    path = tmp_path / "x.json"
    for i in range(5):
        save_json(path, {"n": i})
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_failed_write_leaves_original_intact(tmp_path, monkeypatch):
    """原子寫入的重點：寫到一半失敗，讀到的仍是完整的舊內容。"""
    path = tmp_path / "x.json"
    save_json(path, {"version": "old"})

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_json(path, {"version": "new"})

    assert load_json(path, {}) == {"version": "old"}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_written_file_is_valid_json_utf8(tmp_path):
    path = tmp_path / "x.json"
    save_json(path, {"名稱": "台積電"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"名稱": "台積電"}
