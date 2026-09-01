"""提醒推播的版面。

以前同一個價格在三個地方長成三個樣子：報價卡片寫「收 4,315.00 元」、
漲跌停推播寫「現價 4,315.00 元」、價格提醒寫「現價 1105.00」——
最後那個連千分位與單位都沒有，台積電觸發時你看到的是「4315.00」。

而且沒有任何測試在看推播長什麼樣，改壞了不會有人知道。
"""
import pytest

from bot.handlers.alert import _push_text
from bot.services.formatting import change_str, money, price_with_change, quote_line


def test_price_is_on_the_first_line():
    """Telegram 的通知橫幅只顯示前一兩行。

    價格擺第二行的話，你得點進 app 才知道多少錢、值不值得理它。
    """
    text = _push_text("🚨", "聯發科(2454) 漲停", "2454", 4315.0, 3925.0)
    first = text.splitlines()[0]
    assert "4,315.00 元" in first
    assert "聯發科(2454)" in first and "漲停" in first


def test_thousands_separator_and_unit():
    """「4315.00」一眼讀不出量級，這是實際被抱怨的點。"""
    text = _push_text("🔔", "台積電(2330) 漲破 1100", "2330", 1105.0, 1080.0)
    assert "1,105.00 元" in text
    assert "1105.00" not in text


def test_us_stock_uses_usd():
    text = _push_text("🚨", "NVIDIA(NVDA) 單日跌逾 10%", "NVDA", 217.55, 241.72)
    assert "217.55 USD" in text and "元" not in text


def test_change_line_matches_the_quote_card():
    """漲跌的寫法必須跟報價卡片一模一樣，否則又會漂開。"""
    text = _push_text("🚨", "聯發科(2454) 漲停", "2454", 4315.0, 3925.0)
    card = quote_line("2454", {"name": "聯發科", "close": 4315.0,
                               "prev_close": 3925.0, "market": "TW"})
    change = "▲ +9.94%（+390.00）"
    assert change in text and change in card


def test_no_previous_close_degrades_cleanly():
    """拿不到前收就只寫價格，不要留一行空的或寫 0%。"""
    text = _push_text("🚨", "NVIDIA(NVDA) 單日漲逾 10%", "NVDA", 217.55, None)
    assert text == "🚨 NVIDIA(NVDA) 單日漲逾 10%　217.55 USD"
    assert "\n" not in text


def test_optional_tail_and_footer():
    text = _push_text("🔔", "台積電(2330) 漲破 1100", "2330", 1105.0, 1080.0,
                      tail="　前收 1,080.00", footer="此提醒已自動移除")
    lines = text.splitlines()
    assert len(lines) == 3
    assert lines[1].endswith("前收 1,080.00")
    assert lines[2] == "此提醒已自動移除"


@pytest.mark.parametrize("price,prev,market", [
    (4315.0, 3925.0, "TW"), (217.55, 241.72, "US"), (108.45, 108.45, "TW"),
])
def test_shared_formatter_is_the_only_implementation(price, prev, market):
    """推播與報價共用同一份金額與漲跌實作，不准有第二份。

    推播把金額放第一行、漲跌放第二行，所以不會出現 price_with_change
    合併後的字串——但**兩個組成部分**必須逐字相同。
    """
    ticker = "2330" if market == "TW" else "NVDA"
    text = _push_text("🔔", "x", ticker, price, prev)
    assert money(price, market) in text
    if change_str(price, prev):
        assert change_str(price, prev) in text
    # price_with_change 也是由這兩個組成的，三者不會各走各的
    assert price_with_change(price, prev, market).startswith(money(price, market))
