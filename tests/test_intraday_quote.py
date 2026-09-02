"""盤中報價：保證算出來的是**今天**的漲跌。

這裡鎖住三個實際踩過的坑，三個都會產生「看起來很合理但其實是錯的」數字：

  1. fast_info.previous_close 給錯的前收（2026-09-01 實測：台積電說 2,395，
     那是當天開盤價；南亞科說 549，什麼都不是）
  2. 開盤後幾分鐘 yfinance 還沒產出當日日線，於是「倒數第一列 vs 倒數第二列」
     算出來的是**昨天**的漲跌（2026-09-02 09:03 把昨天的聯發科漲停當成今天
     推播出去）
  3. 台股走 TWSE 盤後結算，盤中查 get_stock_summary 只拿得到前一日收盤
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import bot.services.stock as stock

TAIPEI = "Asia/Taipei"

# 把「現在」釘在事故發生的那一刻：2026-09-02 09:03 台北（開盤後三分鐘）。
# 同一瞬間紐約是 2026-09-01 21:03——美股與台股的「今天」本來就不同天，
# 不釘死的話這些測試會隨執行時間飄。
NOW = datetime(2026, 9, 2, 9, 3, tzinfo=ZoneInfo(TAIPEI))


@pytest.fixture(autouse=True)
def _freeze_now(monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(stock, "datetime", _FixedDatetime)


def _frame(rows, tz=TAIPEI):
    """rows = [(YYYY-MM-DD, close), ...]"""
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz=tz) for d, _ in rows])
    return pd.DataFrame({"Close": [c for _, c in rows]}, index=idx)


class _FakeTicker:
    def __init__(self, frame, live=None):
        self._frame, self._live = frame, live

    def history(self, period="5d"):
        return self._frame

    @property
    def fast_info(self):
        class _FI:
            last_price = self._live

            @property
            def previous_close(inner):
                raise AssertionError(
                    "不要用 fast_info.previous_close——它給的前收是錯的"
                )
        return _FI()


def _patch(monkeypatch, table):
    monkeypatch.setattr(stock.yf, "Ticker", lambda sym: table[sym])


def _tp(offset_days=0):
    """台北的今天往前推 N 天。"""
    return (NOW.date() - timedelta(days=offset_days)).isoformat()


def _ny(offset_days=0):
    """紐約的今天往前推 N 天（台北早上九點時，紐約還是前一天晚上）。"""
    ny = NOW.astimezone(ZoneInfo("America/New_York")).date()
    return (ny - timedelta(days=offset_days)).isoformat()


# ── 正常情況 ──────────────────────────────────────────────────────────

def test_uses_todays_row_when_it_exists(monkeypatch):
    _patch(monkeypatch, {"2454.TW": _FakeTicker(_frame([
        (_tp(2), 3925.0), (_tp(1), 4315.0), (_tp(0), 4295.0),
    ]))})
    assert stock._intraday_sync("2454") == (4295.0, 4315.0)


def test_never_touches_fast_info_previous_close(monkeypatch):
    """假物件一碰 previous_close 就斷言失敗——碰到就代表改回舊做法了。"""
    _patch(monkeypatch, {"2330.TW": _FakeTicker(_frame([
        (_tp(1), 2405.0), (_tp(0), 2440.0),
    ]))})
    assert stock._intraday_sync("2330") == (2440.0, 2405.0)


# ── 開盤後幾分鐘，今天的日線還沒出現 ──────────────────────────────────

def test_yesterdays_move_is_never_reported_as_todays(monkeypatch):
    """實測 2026-09-02 09:03 的誤報：把 9/1 的漲停當成 9/2 的推出去。

    當時 history 的最後一列還是 9/1，程式用「倒數第一 vs 倒數第二」，
    算出 4,315 對 3,925 ＝ +9.94% ＝ 漲停——那是**昨天**的事。
    """
    yesterday_only = _frame([(_tp(2), 3925.0), (_tp(1), 4315.0)])
    _patch(monkeypatch, {"2454.TW": _FakeTicker(yesterday_only, live=4295.0)})

    price, prev = stock._intraday_sync("2454")
    assert (price, prev) == (4295.0, 4315.0), "沒有改用即時價"
    assert prev != 3925.0, "又把昨天的前收當成今天的了"
    assert (price - prev) / prev * 100 == pytest.approx(-0.46, abs=0.01)


def test_no_live_price_means_no_answer(monkeypatch):
    """今天的日線還沒出現、又拿不到即時價 → 回 None，讓呼叫端跳過。

    寧可這一輪不推，十分鐘後那一輪會補上；拿昨天的兩列硬算會誤報。
    """
    _patch(monkeypatch, {"2454.TW": _FakeTicker(
        _frame([(_tp(2), 3925.0), (_tp(1), 4315.0)]), live=None)})
    assert stock._intraday_sync("2454") == (None, None)


def test_stale_live_price_degrades_to_zero_change(monkeypatch):
    """即時價如果也還停在昨天收盤，算出來是 0%——不會誤判成異動。"""
    _patch(monkeypatch, {"2454.TW": _FakeTicker(
        _frame([(_tp(2), 3925.0), (_tp(1), 4315.0)]), live=4315.0)})
    price, prev = stock._intraday_sync("2454")
    assert price == prev == 4315.0


# ── 美股用自己的交易所日期 ────────────────────────────────────────────

def test_us_market_uses_new_york_date(monkeypatch):
    """台北早上九點是紐約前一天晚上。

    用台北日期去判斷美股，會把「紐約剛收的那一列」當成過期資料，
    整片美股都退到即時價路徑。所以要比對**該列自己帶的時區**的當地日期。
    """
    _patch(monkeypatch, {"NVDA": _FakeTicker(_frame(
        [(_ny(1), 217.55), (_ny(0), 220.78)], tz="America/New_York"))})
    assert stock._intraday_sync("NVDA") == (220.78, 217.55)


# ── 邊界 ──────────────────────────────────────────────────────────────

def test_otc_fallback(monkeypatch):
    _patch(monkeypatch, {
        "6488.TW": _FakeTicker(_frame([])),
        "6488.TWO": _FakeTicker(_frame([(_tp(1), 500.0), (_tp(0), 520.0)])),
    })
    assert stock._intraday_sync("6488") == (520.0, 500.0)


def test_single_row_today_has_no_previous_close(monkeypatch):
    """只有今天一列（剛上市）就誠實回 None，不要拿自己當前收算出 0%。"""
    _patch(monkeypatch, {"NVDA": _FakeTicker(_frame([(_ny(0), 220.0)],
                                                    tz="America/New_York"))})
    assert stock._intraday_sync("NVDA") == (220.0, None)


def test_no_data_at_all(monkeypatch):
    _patch(monkeypatch, {"NVDA": _FakeTicker(_frame([]))})
    assert stock._intraday_sync("NVDA") == (None, None)


def test_nan_rows_are_dropped(monkeypatch):
    """yfinance 偶爾夾帶 NaN 列，直接取 iloc[-1] 會拿到 NaN。"""
    _patch(monkeypatch, {"NVDA": _FakeTicker(_frame(
        [(_ny(2), 200.0), (_ny(1), 210.0), (_ny(0), float("nan"))],
        tz="America/New_York"), live=None)})
    # 最後一列被 dropna 掉之後，最新的是「昨天」→ 走即時價路徑
    assert stock._intraday_sync("NVDA") == (None, None)
