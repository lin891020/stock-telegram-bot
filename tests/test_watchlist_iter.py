import json

import pytest

import bot.services.watchlist as watchlist
from bot.services.watchlist import all_tickers, iter_watchlists


@pytest.fixture(autouse=True)
def tmp_watchlist(tmp_path, monkeypatch):
    path = tmp_path / "watchlist.json"
    monkeypatch.setattr(watchlist, "_FILE", path)
    return path


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_iter_normalises_legacy_list_format(tmp_watchlist):
    """舊格式是 list，新格式是 {ticker: name}。遷移只該在一個地方處理。"""
    _write(tmp_watchlist, {"1": ["2330", "AAPL"], "2": {"NVDA": "輝達"}})
    assert dict(iter_watchlists()) == {
        "1": {"2330": "2330", "AAPL": "AAPL"},
        "2": {"NVDA": "輝達"},
    }


def test_iter_skips_empty_users(tmp_watchlist):
    _write(tmp_watchlist, {"1": [], "2": {}, "3": {"TSLA": "特斯拉"}})
    assert [uid for uid, _ in iter_watchlists()] == ["3"]


def test_all_tickers_dedupes_and_keeps_order(tmp_watchlist):
    _write(tmp_watchlist, {"1": {"2330": "台積電", "NVDA": "輝達"}, "2": ["NVDA", "AAPL"]})
    assert all_tickers() == ["2330", "NVDA", "AAPL"]


def test_missing_file_yields_nothing():
    assert list(iter_watchlists()) == []
    assert all_tickers() == []
