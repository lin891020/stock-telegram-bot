"""盤中報價的前收來源。

前收是漲跌停價與 ±5% 提醒的分母，錯了會漏報或誤報。

實測 2026-09-01，yfinance 的 fast_info.previous_close 給的是錯的：
    台積電  說 2,395（那是當天開盤價）  正確 2,405
    南亞科  說   549（什麼都不是）      正確   543
    聯發科  說 3,925  ✓ 剛好對
所以改用日線的倒數第二列。這裡鎖住那個決定。
"""
import pandas as pd
import pytest

import bot.services.stock as stock


class _FakeTicker:
    def __init__(self, closes, symbol=""):
        self._closes, self.symbol = closes, symbol

    def history(self, period="5d"):
        return pd.DataFrame({"Close": self._closes})

    @property
    def fast_info(self):  # 存在但不該被用到
        raise AssertionError("不要再用 fast_info 取前收——它給的前收是錯的")


def _patch(monkeypatch, table):
    monkeypatch.setattr(stock.yf, "Ticker", lambda sym: _FakeTicker(table[sym], sym))


def test_previous_close_is_the_second_last_daily_close(monkeypatch):
    _patch(monkeypatch, {"2330.TW": [2375.0, 2400.0, 2415.0, 2405.0, 2440.0]})
    price, prev = stock._intraday_sync("2330")
    assert (price, prev) == (2440.0, 2405.0)


def test_does_not_touch_fast_info(monkeypatch):
    """_FakeTicker.fast_info 會直接斷言失敗——碰到就代表改回舊做法了。"""
    _patch(monkeypatch, {"2330.TW": [100.0, 110.0]})
    assert stock._intraday_sync("2330") == (110.0, 100.0)


def test_otc_fallback(monkeypatch):
    """上櫃股票的 .TW 沒資料，要退到 .TWO。"""
    _patch(monkeypatch, {"6488.TW": [], "6488.TWO": [500.0, 520.0]})
    assert stock._intraday_sync("6488") == (520.0, 500.0)


def test_single_row_has_no_previous_close(monkeypatch):
    """只有一列（剛上市）就誠實回 None，不要拿自己當前收算出 0%。"""
    _patch(monkeypatch, {"NVDA": [220.0]})
    assert stock._intraday_sync("NVDA") == (220.0, None)


def test_no_data_returns_nothing(monkeypatch):
    _patch(monkeypatch, {"NVDA": []})
    assert stock._intraday_sync("NVDA") == (None, None)


def test_nan_rows_are_dropped(monkeypatch):
    """yfinance 偶爾會夾帶 NaN 列，直接取 iloc[-1] 會拿到 NaN。"""
    _patch(monkeypatch, {"NVDA": [200.0, 210.0, float("nan")]})
    price, prev = stock._intraday_sync("NVDA")
    assert (price, prev) == (210.0, 200.0)
