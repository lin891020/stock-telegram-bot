from bot.services.news import _price_overview


def _p(name, price, prev, market="TW"):
    return {"name": name, "price": price, "prev_close": prev, "market": market}


PRICES = {
    "2408": _p("南亞科", 396.5, 360.5),
    "2330": _p("台積電", 2370.0, 2425.0),
    "TSLA": _p("Tesla", 322.08, 311.2, "US"),
    "AAPL": _p("Apple", 303.42, 308.9, "US"),
}


def test_both_markets_get_headers():
    out = _price_overview(["2408", "2330"], ["TSLA", "AAPL"], PRICES)
    lines = out.splitlines()
    assert lines[0] == "💼 自選股行情"
    assert "🇹🇼 台股" in lines
    assert "🇺🇸 美股" in lines
    # 台股區塊整個排在美股之前
    assert lines.index("🇹🇼 台股") < lines.index("🇺🇸 美股")
    assert out.index("南亞科(2408)") < out.index("🇺🇸 美股")
    assert out.index("Tesla(TSLA)") > out.index("🇺🇸 美股")


def test_single_market_omits_headers():
    out = _price_overview(["2408", "2330"], [], PRICES)
    assert "🇹🇼 台股" not in out
    assert "🇺🇸 美股" not in out
    assert "南亞科(2408)" in out


def test_us_only():
    out = _price_overview([], ["TSLA"], PRICES)
    assert "🇺🇸 美股" not in out
    assert "Tesla(TSLA)" in out


def test_lines_keep_pct_and_warning():
    out = _price_overview(["2408"], [], PRICES)
    assert "▲ +9.99%" in out
    assert "⚠️" in out  # 漲跌 >= 3% 標警示


# ---- 晨報的台股資料日期 -------------------------------------------------

def _tw(date_str="2026/08/28"):
    return {"market": "TW", "name": "台積電", "close": 2420.0,
            "prev_close": 2410.0, "date": date_str}


def _us():
    return {"market": "US", "name": "NVIDIA", "price": 217.5, "prev_close": 228.0}


def test_morning_report_marks_taiwan_data_date():
    """晨報是每天都會看的東西，卻是整個 bot 裡最含糊的地方。

    台股走 TWSE 盤後結算，這裡只印裸數字，看起來跟旁邊接近即時的
    美股一模一樣——連 quote_line 的「收」都沒有。
    """
    from bot.services.news import _price_overview
    out = _price_overview(["2330"], ["NVDA"], {"2330": _tw(), "NVDA": _us()})
    assert "🇹🇼 台股（8/28 收盤）" in out
    assert "🇺🇸 美股\n" in out, "美股接近即時，不該掛日期"


def test_no_date_when_quotes_disagree():
    """兩支台股資料日期不同時不標——標了會有一支是錯的。"""
    from bot.services.news import _price_overview
    prices = {"2330": _tw("2026/08/28"), "2454": _tw("2026/08/27")}
    out = _price_overview(["2330", "2454"], ["NVDA"], {**prices, "NVDA": _us()})
    assert "收盤）" not in out


def test_no_date_when_it_is_missing():
    from bot.services.news import _price_overview
    out = _price_overview(["2330"], ["NVDA"], {"2330": _tw(""), "NVDA": _us()})
    assert "收盤）" not in out
