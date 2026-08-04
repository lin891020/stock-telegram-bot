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
