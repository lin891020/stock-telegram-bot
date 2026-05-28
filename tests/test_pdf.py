# tests/test_pdf.py
import pytest
from bot.services.pdf import generate_pdf

def test_generate_pdf_returns_bytes():
    content = "## 商業模式\n台積電是全球最大的晶圓代工廠。\n\n## 風險\n地緣政治風險較高。"
    result = generate_pdf("2330", "完整分析", content)
    assert isinstance(result, bytes)
    assert len(result) > 1000  # PDF should be non-trivial size
    # PDF magic bytes
    assert result[:4] == b"%PDF"

def test_generate_pdf_with_us_stock():
    content = "Apple is a technology company.\n\n## Valuation\nP/E ratio is 28."
    result = generate_pdf("AAPL", "估值分析", content)
    assert result[:4] == b"%PDF"
