import json

import pytest

import bot.services.filings as filings
from bot.services.filings import (
    html_to_text, list_filings, looks_like_earnings_release,
)


@pytest.fixture(autouse=True)
def tmp_cik_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(filings, "_CIK_CACHE", tmp_path / "sec_cik.json")


def test_html_to_text_strips_tags_and_entities():
    html = (
        "<html><style>p{color:red}</style><body><p>Revenue was "
        "&#36;91.0&nbsp;billion</p><script>x()</script>"
        "<p>&#8220;AI factories&#8221; said Huang &amp; team</p></body></html>"
    )
    text = html_to_text(html)
    assert "Revenue was" in text
    assert "billion" in text
    assert '"AI factories" said Huang & team' in text
    # script / style 內容不得混進來
    assert "color:red" not in text
    assert "x()" not in text


def test_html_to_text_collapses_intra_line_whitespace():
    """行內空白壓成單一空格，但段落/列的換行要留著（欄位對應靠它）。"""
    assert html_to_text("<span>a</span>   \n  <span>b</span>") == "a b"
    assert html_to_text("<p>a</p>\n\n   <p>b</p>") == "a\nb"


def test_detects_us_style_release():
    text = "x" * 2000 + " earnings per share were $2.39 "
    assert looks_like_earnings_release(text)


def test_detects_foreign_issuer_release_without_eps():
    """SK hynix 的 6-K 用 Revenue / Operating Profit，沒有 EPS——只認 EPS 會漏掉。"""
    text = "x" * 2000 + " Revenue 79,318,746 Operating Profit 60,542,608 "
    assert looks_like_earnings_release(text)


def test_rejects_short_cover_page():
    assert not looks_like_earnings_release("Revenue and operating profit")


def test_rejects_non_earnings_filing():
    """交車數量、人事異動那種 8-K 不該被當成財報。"""
    text = "x" * 2000 + " produced 410,000 vehicles and delivered 466,000 vehicles "
    assert not looks_like_earnings_release(text)


def test_rejects_revenue_only_mention():
    text = "x" * 2000 + " this agreement may affect future revenue "
    assert not looks_like_earnings_release(text)


def _submissions(forms, dates):
    return json.dumps({"filings": {"recent": {
        "form": forms,
        "filingDate": dates,
        "accessionNumber": [f"0001-{i:02d}-000001" for i in range(len(forms))],
        "primaryDocument": [f"doc{i}.htm" for i in range(len(forms))],
    }}})


def test_list_filings_filters_by_form_and_limit(monkeypatch):
    monkeypatch.setattr(filings, "_sec_get", lambda url, timeout=25.0: _submissions(
        ["8-K", "4", "10-Q", "8-K", "8-K"],
        ["2026-07-22", "2026-07-20", "2026-07-19", "2026-04-22", "2026-01-28"],
    ))
    result = list_filings(1, ("8-K",), limit=2)
    assert [f["date"] for f in result] == ["2026-07-22", "2026-04-22"]
    # accession 的連字號要去掉，否則組不出 Archives 路徑
    assert "-" not in result[0]["accession"]


def test_list_filings_survives_bad_payload(monkeypatch):
    monkeypatch.setattr(filings, "_sec_get", lambda url, timeout=25.0: "not json")
    assert list_filings(1, ("8-K",)) == []
    monkeypatch.setattr(filings, "_sec_get", lambda url, timeout=25.0: None)
    assert list_filings(1, ("8-K",)) == []


def test_user_agent_has_contact_form():
    """SEC 會擋掉不含聯絡方式的 User-Agent（純網址回 403，實測過）。"""
    assert "@" in filings.USER_AGENT


def test_table_columns_survive_conversion():
    """多欄財務表壓成一行，數字就對不回標題——實測讓 SK hynix 的季增被讀成年增。"""
    html = (
        "<table><tr><td>Revenue</td></tr>"
        "<tr><td>79,318,746</td><td>131,895,033</td></tr>"
        "<tr><td>52,576,287</td><td>N.A.</td></tr>"
        "<tr><td>256.8</td><td>230.8</td></tr></table>"
    )
    lines = html_to_text(html).split("\n")
    assert lines[0] == "Revenue"
    assert lines[1] == "79,318,746 | 131,895,033"
    assert lines[3] == "256.8 | 230.8"


def test_paragraphs_become_separate_lines():
    assert html_to_text("<p>first</p><p>second</p>").split("\n") == ["first", "second"]


def test_empty_cells_do_not_create_stray_separators():
    out = html_to_text("<tr><td>a</td><td></td><td>b</td></tr>")
    assert out == "a | b"
