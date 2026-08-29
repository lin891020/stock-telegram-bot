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


# ---- 新聞歸屬過濾 -------------------------------------------------------

def test_drops_headlines_about_other_companies():
    """yfinance 對 2330.TW 回傳的五則裡有三則是 NVIDIA 和 Cisco 的。

    而 prompt 又寫著「不要提及其他公司名稱」——模型於是把 NVIDIA 的
    內容改寫成台積電的說法送進晨報。該由程式擋掉的，不要留給模型判斷。
    """
    from bot.services.news import _is_about, _match_terms
    terms = _match_terms("2330", "Taiwan Semiconductor Manufacturing Company Limited")

    assert not _is_about("Nvidia Quietly Became Its Own Market Category", terms)
    assert not _is_about("Morgan Stanley reveals Cisco's quiet edge over rivals", terms)
    assert _is_about("Billionaire Druckenmiller Just Bought Taiwan Semiconductor Stock", terms)


def test_matches_acronyms_used_in_headlines():
    """標題寫「TSMC」，公司全名卻是 Taiwan Semiconductor Manufacturing。"""
    from bot.services.news import _is_about, _match_terms
    terms = _match_terms("2330", "Taiwan Semiconductor Manufacturing Company Limited")
    assert _is_about("How TSMC is Advancing its A14 Technology Roadmap", terms)


def test_generic_company_words_are_not_match_terms():
    """「Company」「Limited」「Group」這種字比對到等於沒過濾。"""
    from bot.services.news import _match_terms
    terms = _match_terms("XYZ", "Example Holdings Company Limited")
    assert "company" not in terms and "limited" not in terms and "holdings" not in terms


def test_ticker_alone_is_enough_to_match():
    from bot.services.news import _is_about, _match_terms
    terms = _match_terms("NVDA", "NVIDIA")
    assert _is_about("Jim Cramer on NVIDIA Corporation (NASDAQ:NVDA)", terms)


def test_no_name_means_no_filtering():
    """名稱拿不到時不過濾——寧可讓使用者自己看標題，也不要全部消失。"""
    from bot.services.news import _match_terms
    terms = _match_terms("2330", "")
    assert terms == {"2330"}


def test_html_entities_in_titles_are_decoded():
    """yfinance 的標題帶 &#x27;，直接 html.escape 會變成 &amp;#x27; 顯示出來。"""
    import html
    raw = "Elon Musk Calls Gavin Newsom&#x27;s Plan"
    assert html.unescape(raw) == "Elon Musk Calls Gavin Newsom's Plan"
