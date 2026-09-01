"""TWSE 回非 JSON 時不該炸掉整張卡片。

實測：按下「聯發科(2454)」的按鈕收到 JSONDecodeError 的 traceback。
TWSE 忙的時候會回 HTTP 200 但內容是 HTML 錯誤頁，resp.json() 就丟
JSONDecodeError——它不是 httpx 的例外，所以漏在重試的 except 之外，
於是不但沒重試，還一路往上炸。而且五個月份是併發抓的，一個月壞掉全毀。
"""
import asyncio
import json

import httpx
import pytest

from bot.services.stock import _fetch_month


class _Resp:
    def __init__(self, body: str, status: int = 200):
        self._body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    def json(self):
        return json.loads(self._body)


class _Client:
    """前 n 次回 HTML 錯誤頁，之後回正常 JSON。"""

    def __init__(self, bad_times: int, body: str | None = None):
        self.bad_times, self.calls = bad_times, 0
        self.body = body or json.dumps({"stat": "OK", "data": [["115/09/01", "1", "2"]]})

    async def get(self, url, **kw):
        self.calls += 1
        if self.calls <= self.bad_times:
            return _Resp("<html><body>System busy</body></html>")
        return _Resp(self.body)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """重試的退避不要真的等。"""
    async def _instant(_):
        return None
    monkeypatch.setattr(asyncio, "sleep", _instant)


@pytest.mark.asyncio
async def test_html_error_page_is_retried_not_raised():
    from datetime import date

    client = _Client(bad_times=1)
    rows = await _fetch_month(client, "2454", date(2026, 9, 1))

    assert client.calls == 2, "非 JSON 的回應沒有觸發重試"
    assert rows == [["115/09/01", "1", "2"]]


@pytest.mark.asyncio
async def test_persistent_garbage_returns_empty_instead_of_raising():
    """一直回垃圾就回空清單，讓上層走 yfinance fallback——但絕不往上拋。"""
    from datetime import date

    client = _Client(bad_times=99)
    rows = await _fetch_month(client, "2454", date(2026, 9, 1))
    assert rows == []


@pytest.mark.asyncio
async def test_one_bad_month_does_not_kill_the_others():
    """五個月份是 gather 併發抓的；以前一個月拋例外，整支查詢就全毀。"""
    from datetime import date
    from bot.services.stock import _MONTHS_TO_FETCH

    class _Mixed:
        def __init__(self):
            self.calls = 0

        async def get(self, url, **kw):
            self.calls += 1
            # 第一個月份永遠壞，其餘正常
            if kw["params"]["date"].startswith("202609"):
                return _Resp("not json at all")
            return _Resp(json.dumps({"stat": "OK", "data": [["115/08/31", "1", "2"]]}))

    client = _Mixed()
    months = [date(2026, 9, 1), date(2026, 8, 1), date(2026, 7, 1)]
    results = await asyncio.gather(
        *[_fetch_month(client, "2454", m) for m in months]
    )
    assert results[0] == [], "壞掉的月份應該回空清單"
    assert all(r for r in results[1:]), "好的月份不該被拖累"
    assert _MONTHS_TO_FETCH >= 2
