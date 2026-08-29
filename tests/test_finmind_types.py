"""鎖住 FinMind 科目名稱這個坑。

寫錯名字 FinMind 不會報錯，只會回空陣列，於是報告默默少一整塊。
這個坑踩過三次：NetIncome（年度淨利）、PropertyAndPlantAndEquipment
（資本支出），以及 TotalLiabilities / StockholdersEquity（總負債與
股東權益）——最後這組讓資產負債表平衡檢查對台股形同不存在。
"""
import re
from pathlib import Path

from bot.services import financials
from bot.services.financials import FINMIND_TYPES

# conftest 會把工作目錄換到暫存區，路徑要從模組自己算
_SRC = Path(financials.__file__).read_text()


def _literals_in_source() -> set[str]:
    """程式裡真的傳給 extract_* 的科目名稱。"""
    calls = re.findall(r"extract_(?:flow|point|cumulative)\(\s*\w+,\s*\"([A-Za-z]+)\"", _SRC)
    return set(calls)


def test_table_matches_the_names_actually_used():
    """FINMIND_TYPES 是 /health 拿去對帳的表，跟實際用的名字漂掉就沒意義了。"""
    declared = {t for group in FINMIND_TYPES.values() for t in group}
    assert _literals_in_source() == declared


def test_liabilities_and_equity_use_finmind_spelling():
    """FinMind 叫 Liabilities / Equity；TotalLiabilities / StockholdersEquity
    是 yfinance 的講法，用在台股上只會靜默回空。"""
    balance = FINMIND_TYPES["TaiwanStockBalanceSheet"]
    assert "Liabilities" in balance and "Equity" in balance
    used = _literals_in_source()
    assert "TotalLiabilities" not in used
    assert "StockholdersEquity" not in used


def test_empty_series_is_logged_not_silent(caplog):
    """整組科目變空時要留下記錄，不能安靜地少一塊。"""
    from bot.services.financials import _warn_empty
    with caplog.at_level("WARNING"):
        _warn_empty("2330", {"revenue": {"2025": 1}})
    assert "型別名稱失效" in caplog.text
    assert "total_liabilities" in caplog.text
    assert "equity" in caplog.text


def test_no_warning_when_everything_present(caplog):
    from bot.services.financials import _warn_empty, _EXPECTED_ANNUAL
    with caplog.at_level("WARNING"):
        _warn_empty("2330", {k: {"2025": 1} for k in _EXPECTED_ANNUAL})
    assert not caplog.text
