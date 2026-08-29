"""使用者實際看到的文字。

這些不是演算法對錯，是「看到之後會不會做錯決定」——台股報價沒標日期
時，盤中查到的其實是昨天的收盤價，畫面上卻沒有任何線索。
"""
from bot.handlers.analyze import _menu_text
from bot.handlers.earnings import _missing_block
from bot.services.formatting import quote_line


def _tw(**kw):
    return {"market": "TW", "name": "台積電", "close": 2420.0, "prev_close": 2410.0, **kw}


def test_taiwan_quote_shows_the_data_date():
    """台股走 TWSE 盤後結算，盤中查到的是昨天的收盤價。

    只寫「收」不夠——使用者無從得知那是哪一天的收盤。
    """
    line = quote_line("2330", _tw(date="2026/08/28"))
    assert "8/28 收盤" in line


def test_us_quote_has_no_date_suffix():
    """美股走 yfinance 接近即時，標日期反而誤導。"""
    line = quote_line("NVDA", {"market": "US", "name": "NVIDIA", "price": 217.5, "prev_close": 228.0})
    assert "收盤）" not in line


def test_missing_date_is_not_guessed():
    """拿不到日期就不寫，不要編一個。"""
    assert "收盤）" not in quote_line("2330", _tw())
    assert "收盤）" not in quote_line("2330", _tw(date=""))


def test_missing_block_lists_items_not_just_a_count():
    """原則是「寧可說查不到」——只報數量等於說了一半。"""
    out = _missing_block(["公司名稱", "官方財測"])
    assert "公司名稱" in out and "官方財測" in out
    assert "2 項" in out


def test_missing_block_collapses_a_long_list():
    out = _missing_block([f"項目{i}" for i in range(9)])
    assert "9 項" in out
    assert "還有 5 項" in out
    assert out.count("　•") == 5   # 4 條 + 1 條收合


def test_no_missing_block_when_nothing_is_missing():
    assert _missing_block([]) == ""


def test_analysis_menu_explains_every_jargon_term():
    """七個術語並排，第一次用的人一個都看不懂。"""
    text = _menu_text("2330")
    for term in ["競爭護城河", "估值分析", "多空辯論", "判斷條件"]:
        assert term in text
        # 每個術語後面都要跟一句白話
        line = next(l for l in text.splitlines() if l.startswith(f"• {term}"))
        assert " — " in line and len(line.split(" — ")[1]) > 5


def test_analysis_menu_sets_expectations_up_front():
    """免責聲明放報告底部沒人讀得到；要在選之前就講。"""
    assert "不會直接告訴你買或賣" in _menu_text("2330")
