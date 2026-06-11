# tests/test_stock.py
import pytest
from unittest.mock import patch, MagicMock
from bot.services.stock import is_taiwan_stock, fetch_us_data, get_stock_summary

def test_is_taiwan_stock_true():
    assert is_taiwan_stock("2330") is True
    assert is_taiwan_stock("0050") is True
    assert is_taiwan_stock("006208") is True

def test_is_taiwan_stock_false():
    assert is_taiwan_stock("TSLA") is False
    assert is_taiwan_stock("AAPL") is False
    assert is_taiwan_stock("META") is False

def test_fetch_us_data_returns_dict():
    mock_info = {
        "longName": "Apple Inc.",
        "currentPrice": 185.5,
        "currency": "USD",
        "trailingPE": 28.5,
        "marketCap": 2_800_000_000_000,
        "profitMargins": 0.25,
        "returnOnEquity": 1.45,
        "sector": "Technology",
    }
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info

    with patch("bot.services.stock.yf.Ticker", return_value=mock_ticker):
        result = fetch_us_data("AAPL")

    assert result["ticker"] == "AAPL"
    # clean_us_name strips corporate suffixes: "Apple Inc." → "Apple"
    assert result["name"] == "Apple"
    assert result["price"] == 185.5
    assert result["market"] == "US"
    assert "pe_ratio" in result
