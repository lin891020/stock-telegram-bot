# Telegram Investment Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram Bot that provides stock analysis (7 Wall Street prompts → PDF) and a personal finance coaching dialogue for a beginner investor, deployed 24/7 on Render.com.

**Architecture:** State-machine bot using `python-telegram-bot` v20 (fully async). Three independent handler modules (analyze, finance, learn) wired into a single `main.py`. Services (stock data, LLM, PDF, GitHub storage) are pure functions imported by handlers. The bot uses polling mode — no webhook or public URL needed.

**Tech Stack:** `python-telegram-bot==20.7`, `anthropic`, `openai` (for GitHub Models fallback), `yfinance`, `reportlab`, `httpx`, `requests`, `python-dotenv`, `pytest`, `pytest-asyncio`

**Spec:** `../../../docs/superpowers/specs/2026-05-27-telegram-investment-bot-design.md` (in stock-assistant repo)

**Working directory for all tasks:** `/Users/lin1020/Projects/stock-telegram-bot/`

---

## File Map

```
stock-telegram-bot/
├── bot/
│   ├── __init__.py
│   ├── config.py                  # env vars, validated at import
│   ├── auth.py                    # Telegram ID whitelist filter
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── menu.py                # /start → main menu buttons
│   │   ├── analyze.py             # /analyze <ticker> → 7-button → PDF
│   │   ├── learn.py               # /learn <topic> → lesson or Claude
│   │   └── finance.py             # /finance → ConversationHandler (5 states)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── stock.py               # TWSE + yfinance data fetching
│   │   ├── llm.py                 # Claude / gpt-4o-mini wrapper
│   │   ├── pdf.py                 # reportlab PDF generation
│   │   └── github_store.py        # read/write profile.json via GitHub API
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── analysis.py            # 7 Wall Street prompt strings
│   ├── content/
│   │   └── lessons.json           # pre-written educational content
│   └── fonts/                     # .gitkeep + downloaded NotoSansCJK font
├── scripts/
│   └── download_font.py           # one-time font download
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_github_store.py
│   ├── test_stock.py
│   ├── test_llm.py
│   └── test_pdf.py
├── .env.example
├── requirements.txt
├── render.yaml
└── main.py                        # entry point: python main.py
```

---

## Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `bot/__init__.py`, `bot/handlers/__init__.py`, `bot/services/__init__.py`, `bot/prompts/__init__.py`
- Create: `bot/fonts/.gitkeep`
- Create: `tests/conftest.py`
- Create: `main.py` (stub)

- [ ] **Step 1: Init git repo and create directory structure**

```bash
cd /Users/lin1020/Projects/stock-telegram-bot
git init
mkdir -p bot/handlers bot/services bot/prompts bot/content bot/fonts scripts tests
touch bot/__init__.py bot/handlers/__init__.py bot/services/__init__.py bot/prompts/__init__.py
touch bot/fonts/.gitkeep
```

- [ ] **Step 2: Create `requirements.txt`**

```
python-telegram-bot==20.7
anthropic==0.40.0
openai==1.57.0
yfinance==0.2.51
httpx==0.27.2
reportlab==4.2.5
requests==2.32.3
python-dotenv==1.0.1
pytest==8.3.4
pytest-asyncio==0.24.0
```

- [ ] **Step 3: Create `.env.example`**

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO=yourusername/stock-bot-data
LLM_PROVIDER=anthropic
ALLOWED_TELEGRAM_ID=123456789
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import pytest
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_gh_token")
os.environ.setdefault("GITHUB_REPO", "test/repo")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ALLOWED_TELEGRAM_ID", "123456789")
```

- [ ] **Step 5: Create stub `main.py`**

```python
from bot.config import TELEGRAM_BOT_TOKEN

if __name__ == "__main__":
    print(f"Bot token loaded: {TELEGRAM_BOT_TOKEN[:10]}...")
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: project scaffold"
```

---

## Task 2: config.py

**Files:**
- Create: `bot/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
import os

def test_config_loads_required_vars(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("ALLOWED_TELEGRAM_ID", "999")
    # Re-import to pick up monkeypatched values
    import importlib
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.TELEGRAM_BOT_TOKEN == "abc123"
    assert cfg.ALLOWED_TELEGRAM_ID == 999

def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    import importlib
    import bot.config as cfg
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        importlib.reload(cfg)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `bot.config` doesn't exist yet.

- [ ] **Step 3: Create `bot/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value

TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.environ.get("GITHUB_REPO", "")
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic")
ALLOWED_TELEGRAM_ID: int = int(_require("ALLOWED_TELEGRAM_ID"))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Create `bot/auth.py`**

```python
from telegram.ext import filters as tg_filters
from bot.config import ALLOWED_TELEGRAM_ID

def build_auth_filter():
    """Returns a filter that only passes messages from the allowed Telegram user."""
    return tg_filters.User(user_id=ALLOWED_TELEGRAM_ID)
```

- [ ] **Step 6: Commit**

```bash
git add bot/config.py bot/auth.py tests/test_config.py tests/conftest.py
git commit -m "feat: config and auth filter"
```

---

## Task 3: github_store.py

**Files:**
- Create: `bot/services/github_store.py`
- Create: `tests/test_github_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_github_store.py
import pytest
import json
import base64
from unittest.mock import patch, MagicMock
from bot.services.github_store import read_profile, write_profile

def _make_github_response(data: dict) -> MagicMock:
    """Helper: mock a GitHub API GET response with encoded JSON."""
    content = base64.b64encode(json.dumps(data).encode()).decode()
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"content": content + "\n", "sha": "abc123"}
    mock.raise_for_status = MagicMock()
    return mock

def test_read_profile_returns_dict():
    profile = {"monthly_income": 50000, "goal": "緊急備用金"}
    with patch("bot.services.github_store.requests.get", return_value=_make_github_response(profile)):
        result = read_profile()
    assert result["monthly_income"] == 50000
    assert result["goal"] == "緊急備用金"

def test_read_profile_returns_empty_on_404():
    mock = MagicMock()
    mock.status_code = 404
    with patch("bot.services.github_store.requests.get", return_value=mock):
        result = read_profile()
    assert result == {}

def test_write_profile_calls_put():
    get_mock = _make_github_response({})
    put_mock = MagicMock()
    put_mock.raise_for_status = MagicMock()
    
    with patch("bot.services.github_store.requests.get", return_value=get_mock), \
         patch("bot.services.github_store.requests.put", return_value=put_mock) as mock_put:
        write_profile({"monthly_income": 60000})
    
    mock_put.assert_called_once()
    call_json = mock_put.call_args[1]["json"]
    assert call_json["sha"] == "abc123"
    decoded = json.loads(base64.b64decode(call_json["content"]).decode())
    assert decoded["monthly_income"] == 60000
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_github_store.py -v
```

Expected: `ModuleNotFoundError` — `bot.services.github_store` doesn't exist yet.

- [ ] **Step 3: Create `bot/services/github_store.py`**

```python
import base64
import json
import requests
from bot.config import GITHUB_TOKEN, GITHUB_REPO

_PROFILE_PATH = "profile.json"
_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def _api_url() -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_PROFILE_PATH}"

def read_profile() -> dict:
    """Read user profile JSON from GitHub. Returns {} if file doesn't exist."""
    resp = requests.get(_api_url(), headers=_HEADERS, timeout=10)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    raw = base64.b64decode(resp.json()["content"]).decode()
    return json.loads(raw)

def write_profile(data: dict) -> None:
    """Write user profile JSON to GitHub, creating or updating the file."""
    url = _api_url()
    get_resp = requests.get(url, headers=_HEADERS, timeout=10)
    sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

    encoded = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode()
    ).decode()

    payload: dict = {"message": "Update user profile", "content": encoded}
    if sha:
        payload["sha"] = sha

    requests.put(url, headers=_HEADERS, json=payload, timeout=10).raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_github_store.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/services/github_store.py tests/test_github_store.py
git commit -m "feat: GitHub profile storage service"
```

---

## Task 4: stock.py — ticker detection and US stocks

**Files:**
- Create: `bot/services/stock.py`
- Create: `tests/test_stock.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    assert result["name"] == "Apple Inc."
    assert result["price"] == 185.5
    assert result["market"] == "US"
    assert "pe_ratio" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_stock.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `bot/services/stock.py` with ticker detection and US data**

```python
import re
import asyncio
import httpx
import yfinance as yf
from datetime import date, timedelta

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
_MONTHS_TO_FETCH = 3
_MAX_RETRIES = 3

def is_taiwan_stock(ticker: str) -> bool:
    """Return True if ticker looks like a Taiwan stock code (4–6 digits)."""
    return bool(re.match(r'^\d{4,6}$', ticker.strip()))

def fetch_us_data(ticker: str) -> dict:
    """Fetch financial summary for a US stock using yfinance."""
    stock = yf.Ticker(ticker)
    info = stock.info
    return {
        "ticker": ticker,
        "name": info.get("longName", ticker),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "currency": info.get("currency", "USD"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "revenue_growth": info.get("revenueGrowth"),
        "gross_margins": info.get("grossMargins"),
        "profit_margins": info.get("profitMargins"),
        "operating_margins": info.get("operatingMargins"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "debt_to_equity": info.get("debtToEquity"),
        "free_cashflow": info.get("freeCashflow"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market": "US",
    }

def _months_to_query(reference: date) -> list[date]:
    result = []
    current = reference.replace(day=1)
    for _ in range(_MONTHS_TO_FETCH):
        result.append(current)
        current = (current - timedelta(days=1)).replace(day=1)
    return result

def _roc_to_ad(roc_date: str) -> str:
    parts = roc_date.split("/")
    return f"{int(parts[0]) + 1911}/{parts[1]}/{parts[2]}"

async def _fetch_month(client: httpx.AsyncClient, stock_no: str, query_date: date) -> list:
    params = {"stockNo": stock_no, "date": query_date.strftime("%Y%m%d"), "response": "json"}
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.get(TWSE_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []) if data.get("stat") == "OK" else []
        except (httpx.HTTPStatusError, httpx.RequestError):
            if attempt == _MAX_RETRIES - 1:
                return []
            await asyncio.sleep(2 ** attempt)
    return []

async def fetch_taiwan_data(ticker: str) -> dict:
    """Fetch recent price data for a Taiwan stock from TWSE."""
    query_dates = _months_to_query(date.today())
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch_month(client, ticker, d) for d in query_dates])

    all_rows = [row for monthly in results for row in monthly]
    if not all_rows:
        return {"ticker": ticker, "error": f"查無股票代號 {ticker}", "market": "TW"}

    # Get latest row (index 0=date, 1=volume, 4=open, 6=close)
    latest = all_rows[-1]
    close = latest[6].replace(",", "") if len(latest) > 6 else "N/A"
    volume = latest[1].replace(",", "") if len(latest) > 1 else "N/A"

    return {
        "ticker": ticker,
        "date": _roc_to_ad(latest[0]),
        "close": float(close) if close != "N/A" else None,
        "volume": float(volume) if volume != "N/A" else None,
        "market": "TW",
        "data_rows": len(all_rows),
    }

async def get_stock_summary(ticker: str) -> dict:
    """Main entry point: auto-detect Taiwan vs US stock and fetch data."""
    ticker = ticker.upper().strip()
    if is_taiwan_stock(ticker):
        return await fetch_taiwan_data(ticker)
    return fetch_us_data(ticker)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_stock.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/services/stock.py tests/test_stock.py
git commit -m "feat: stock data service (TWSE + yfinance)"
```

---

## Task 5: llm.py

**Files:**
- Create: `bot/services/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm.py
import pytest
from unittest.mock import patch, MagicMock
from bot.services.llm import call_llm

def _mock_anthropic_response(text: str):
    mock_content = MagicMock()
    mock_content.text = text
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]
    return mock_resp

def test_call_llm_anthropic_returns_string(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    import importlib, bot.services.llm as llm_mod
    importlib.reload(llm_mod)

    mock_create = MagicMock(return_value=_mock_anthropic_response("分析結果"))
    with patch.object(llm_mod.anthropic.Anthropic, "__init__", return_value=None), \
         patch("bot.services.llm.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create = mock_create
        result = llm_mod.call_llm("你是分析師", "分析台積電")

    assert isinstance(result, str)

def test_call_llm_returns_nonempty():
    mock_content = MagicMock()
    mock_content.text = "這是分析報告"
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]

    with patch("bot.services.llm.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_resp
        result = call_llm("system", "user")

    assert len(result) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_llm.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `bot/services/llm.py`**

```python
import anthropic as _anthropic
from openai import OpenAI
from bot.config import ANTHROPIC_API_KEY, GITHUB_TOKEN, LLM_PROVIDER

# Use Sonnet for deep analysis, Haiku for conversational finance coach
ANTHROPIC_ANALYSIS_MODEL = "claude-sonnet-4-6"
ANTHROPIC_CHAT_MODEL = "claude-haiku-4-5-20251001"
GITHUB_MODEL = "gpt-4o-mini"
GITHUB_BASE_URL = "https://models.inference.ai.azure.com"


def call_llm(system: str, user: str, model: str = ANTHROPIC_ANALYSIS_MODEL) -> str:
    """Synchronous LLM call. Returns full response text.

    In async handlers, wrap with: await asyncio.to_thread(call_llm, system, user)
    """
    if LLM_PROVIDER == "anthropic":
        return _call_anthropic(system, user, model)
    return _call_github(system, user)


def _call_anthropic(system: str, user: str, model: str) -> str:
    client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _call_github(system: str, user: str) -> str:
    client = OpenAI(api_key=GITHUB_TOKEN, base_url=GITHUB_BASE_URL)
    response = client.chat.completions.create(
        model=GITHUB_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_llm.py -v
```

Expected: PASS (note: tests use mocks, no real API calls).

- [ ] **Step 5: Commit**

```bash
git add bot/services/llm.py tests/test_llm.py
git commit -m "feat: LLM service (Claude + GitHub Models)"
```

---

## Task 6: pdf.py + font download

**Files:**
- Create: `scripts/download_font.py`
- Create: `bot/services/pdf.py`
- Create: `tests/test_pdf.py`

- [ ] **Step 1: Create `scripts/download_font.py`**

```python
"""Download NotoSansCJK font for Chinese PDF rendering. Run once before first use."""
import os
import urllib.request

FONT_URL = (
    "https://github.com/googlefonts/noto-cjk/raw/main/Sans/SubsetOTF/TC/"
    "NotoSansTC-Regular.otf"
)
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "bot", "fonts", "NotoSansTC-Regular.otf")

def download_font():
    font_path = os.path.abspath(FONT_PATH)
    if os.path.exists(font_path):
        print(f"Font already exists: {font_path}")
        return
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    print("Downloading NotoSansTC font (~3MB)...")
    urllib.request.urlretrieve(FONT_URL, font_path)
    print(f"Font saved to: {font_path}")

if __name__ == "__main__":
    download_font()
```

- [ ] **Step 2: Download the font**

```bash
python scripts/download_font.py
```

Expected: `Font saved to: .../bot/fonts/NotoSansTC-Regular.otf`

- [ ] **Step 3: Write the failing test**

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
pytest tests/test_pdf.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 5: Create `bot/services/pdf.py`**

```python
import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_NAME = "NotoSans"
_FONT_REGISTERED = False

def _ensure_font() -> str:
    """Register CJK font if available. Returns font name to use."""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_NAME

    font_path = os.path.join(
        os.path.dirname(__file__), "..", "fonts", "NotoSansTC-Regular.otf"
    )
    font_path = os.path.abspath(font_path)

    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont(_FONT_NAME, font_path))
        _FONT_REGISTERED = True
        return _FONT_NAME

    return "Helvetica"  # fallback (no CJK support, but won't crash)


def generate_pdf(ticker: str, analysis_type: str, content: str) -> bytes:
    """Generate a PDF report and return raw bytes."""
    font = _ensure_font()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2.5 * cm, leftMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )

    title_style = ParagraphStyle(
        "ReportTitle", fontName=font, fontSize=16, leading=22,
        spaceAfter=8, textColor=colors.HexColor("#1a1a2e"),
    )
    heading_style = ParagraphStyle(
        "ReportHeading", fontName=font, fontSize=13, leading=18,
        spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "ReportBody", fontName=font, fontSize=10, leading=16, spaceAfter=4,
    )

    story = [
        Paragraph(f"{ticker} — {analysis_type}", title_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")),
        Spacer(1, 0.3 * cm),
    ]

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.2 * cm))
            continue

        # Escape XML special characters
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if line.startswith("### ") or line.startswith("## "):
            story.append(Paragraph(safe.lstrip("# "), heading_style))
        elif line.startswith("**") and line.endswith("**"):
            story.append(Paragraph(f"<b>{safe[2:-2]}</b>", body_style))
        elif line.startswith("• ") or line.startswith("- "):
            story.append(Paragraph(f"&bull; {safe[2:]}", body_style))
        else:
            story.append(Paragraph(safe, body_style))

    doc.build(story)
    return buffer.getvalue()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_pdf.py -v
```

Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/download_font.py bot/services/pdf.py tests/test_pdf.py bot/fonts/.gitkeep
git commit -m "feat: PDF generation service with CJK font support"
```

---

## Task 7: Analysis prompts and educational content

**Files:**
- Create: `bot/prompts/analysis.py`
- Create: `bot/content/lessons.json`

- [ ] **Step 1: Create `bot/prompts/analysis.py`**

```python
# 7 Wall Street analyst prompts. Each accepts {ticker} via .format().
PROMPTS: dict[str, str] = {
    "full": """以華爾街資深股票分析師的角度，對股票 {ticker} 進行完整分析，包括：
• 商業模式與收入來源
• 競爭優勢（護城河）
• 產業趨勢
• 財務健康狀況（營收成長、利潤率、負債）
• 關鍵風險
• 與競爭對手的估值比較
• 多頭、空頭與基本情境分析
• 未來 12–24 個月展望
請用簡單易懂的方式解釋，但保有專業分析深度。""",

    "financial": """分析 {ticker} 過去 5 年的財務數據，拆解：
• 營收成長
• 淨利趨勢
• 自由現金流
• 利潤率
• 負債水準
• 股東權益報酬率（ROE）
並判斷這家公司目前是財務體質正在變強，還是開始走弱。""",

    "moat": """評估 {ticker} 的競爭護城河，分析：
• 品牌影響力
• 網路效應
• 轉換成本
• 成本優勢
• 專利或獨家技術
並與主要競爭對手比較，最後幫這家公司的護城河強度打分（1–10 分）。""",

    "valuation": """對 {ticker} 進行估值分析（如投資銀行研究報告），包含：
• 本益比（P/E）與同業比較
• 折現現金流（DCF）估值
• 產業平均估值水準
• 是否被低估或高估的結論""",

    "growth": """分析 {ticker} 的未來成長潛力，考慮：
• 市場規模
• 產業成長率
• 擴張機會
• 新產品
• AI 或技術優勢
並評估未來 5–10 年的潛在成長空間。""",

    "debate": """以兩位分析師的對話方式，針對 {ticker} 進行多空辯論。
一位為多頭觀點（看漲），一位為空頭觀點（看跌）。
雙方都必須提出有數據支持的論點。
最後請給出一個相對中性的結論。""",

    "recommendation": """評估是否應該投資 {ticker}，包含：
• 短期展望（1年內）
• 長期展望（5年以上）
• 關鍵催化因素
• 主要風險
• 最終結論：買入、持有或避免""",
}

ANALYSIS_BUTTONS = [
    ("📊 完整分析", "full"),
    ("💹 財務健康", "financial"),
    ("🏰 競爭護城河", "moat"),
    ("💰 估值分析", "valuation"),
    ("🚀 成長潛力", "growth"),
    ("⚖️ 多空辯論", "debate"),
    ("✅ 投資建議", "recommendation"),
]
```

- [ ] **Step 2: Create `bot/content/lessons.json`**

```json
{
  "ETF": "📚 **什麼是 ETF？**\n\nETF（Exchange-Traded Fund，指數股票型基金）是一種可以在股票市場買賣的基金，就像買一籃子股票。\n\n**為什麼適合新手？**\n• 一次買到很多公司（分散風險）\n• 費用比主動型基金低很多\n• 買賣和股票一樣方便\n\n**台灣常見 ETF：**\n• 0050 — 追蹤台灣前50大公司\n• 0056 — 高股息ETF\n• 00878 — 國泰永續高股息\n\n**新手建議：** 從 0050 開始，用定期定額每月投入固定金額，不需要管市場漲跌。",

  "指數基金": "📚 **什麼是指數基金？**\n\n指數基金是追蹤「指數」的基金。指數就像一個股市的溫度計，例如台灣加權指數代表台股整體表現。\n\n**指數基金的邏輯：** 與其選個股，不如買整個市場。長期來看，大多數主動基金都跑輸指數。\n\n**巴菲特的建議：** 他曾說，對大多數投資人來說，定期買入低成本的指數基金是最好的投資方式。\n\n**和 ETF 的關係：** 很多 ETF 就是指數基金（例如 0050 追蹤台灣50指數），可以把它們視為同一類。",

  "緊急備用金": "📚 **什麼是緊急備用金？**\n\n緊急備用金是你存在活存帳戶（隨時可領）的錢，專門應對突發狀況：失業、醫療、車子壞掉等。\n\n**要存多少？**\n一般建議存 3–6 個月的生活費。例如：\n• 每月支出 NT$25,000 → 存 NT$75,000–150,000\n\n**為什麼這麼重要？**\n沒有緊急備用金，一旦遇到突發事件，你可能被迫在市場最低點賣掉投資。有了它，你才能安心長期投資。\n\n**新手第一步：** 在開始投資之前，先把緊急備用金存滿。這是最重要的第一步。",

  "50/30/20": "📚 **50/30/20 法則**\n\n這是最經典的薪水分配方法：\n\n• **50% → 必要支出** — 房租、水電、交通、食物等生活必需\n• **30% → 想要支出** — 娛樂、餐廳、購物、旅遊\n• **20% → 儲蓄/投資** — 緊急備用金、投資、還債\n\n**台灣實際狀況：** 如果在台北租房，50% 可能不夠必要支出，可以調整成 60/20/20。重點是養成先存後花的習慣。\n\n**操作方式：** 薪水一入帳，立刻轉 20% 到另一個帳戶，剩下的才是能花的錢。",

  "複利": "📚 **複利 — 第八大奇蹟**\n\n複利就是「利上加利」。你的獲利也會繼續產生獲利。\n\n**例子：**\n每月投入 NT$5,000，年化報酬率 7%（歷史上台股長期平均）：\n• 10年後：約 NT$867,000\n• 20年後：約 NT$2,606,000\n• 30年後：約 NT$6,091,000\n\n投入總金額只有 NT$1,800,000（30年 × 12月 × 5,000），但最後有 NT$6,091,000！\n\n**複利的關鍵：** 時間。越早開始，效果越驚人。今天比明天早開始一年，長期差距可能是幾十萬。",

  "資產配置": "📚 **什麼是資產配置？**\n\n資產配置就是把錢分散放在不同類型的資產上，降低風險。\n\n**主要資產類型：**\n• 股票 — 高風險高報酬，長期增值\n• 債券 — 低風險低報酬，提供穩定性\n• 現金/定存 — 最安全，但報酬最低\n• 房地產 — 台灣人的最愛，但流動性低\n\n**新手簡單版配置：**\n年輕（20-35歲）：股票 80% + 債券 20%\n中年（35-50歲）：股票 60% + 債券 40%\n退休前（50歲+）：股票 40% + 債券 60%\n\n**最簡單做法：** 買全球股票ETF + 債券ETF，定期再平衡。",

  "股票": "📚 **股票 vs 債券**\n\n**股票：**\n• 你買了公司的一小部分所有權\n• 公司賺錢，你分紅利、股價上漲\n• 公司虧損，股價下跌甚至歸零\n• 長期（10年以上）平均年化報酬約 7-10%\n\n**債券：**\n• 你借錢給政府或公司\n• 固定利息收入，到期還本\n• 風險比股票低，但報酬也低\n• 年化報酬約 2-4%\n\n**何時買債券？** 接近退休、不能承擔大幅虧損時，增加債券比例，讓投資組合更穩定。",

  "定期定額": "📚 **定期定額 — 新手最好的投資方式**\n\n定期定額就是每個月固定投入相同金額買 ETF 或股票，不管市場高低。\n\n**為什麼好？**\n• 市場高點 → 買到少一點份額\n• 市場低點 → 買到多一點份額（平均成本降低）\n• 不需要預測市場時機（連專家都做不到）\n• 養成儲蓄習慣\n\n**怎麼做？**\n在券商設定「定期定額」，每月自動扣款買 0050 或你選的 ETF。最低可以從 NT$1,000/月開始。\n\n**最重要的事：** 堅持下去，不要因為市場下跌就停止。下跌時買更划算。",

  "本益比": "📚 **本益比（P/E Ratio）**\n\n本益比告訴你「買這家公司要花幾年的獲利才能回本」。\n\n**公式：** 股價 ÷ 每股盈餘（EPS）\n\n**例子：** 台積電股價 NT$900，每股賺 NT$45，P/E = 20倍，表示要20年的獲利才能回本。\n\n**怎麼看？**\n• P/E 低 → 相對便宜（但可能有問題）\n• P/E 高 → 相對貴（但可能成長快）\n• 要和同行業比較才有意義\n• 台股平均 P/E 約 14-18 倍\n\n**新手注意：** P/E 只是參考，不能單獨決定買不買。成長型公司（如科技股）通常 P/E 較高。",

  "股息": "📚 **股息（Dividend）**\n\n股息是公司把獲利的一部分直接分給股東的現金。\n\n**股息殖利率：** 每股股息 ÷ 股價 × 100%\n例如：股價 NT$50，每年配息 NT$2 → 殖利率 4%\n\n**台灣特色：** 台灣很多公司和 ETF（如0056、00878）以高股息著名，適合想要現金流的投資人。\n\n**注意事項：**\n• 除息後股價會下調（填息才算真正賺到）\n• 高股息不代表公司很好，要看能否持續賺錢\n• 年輕時更好的策略可能是把股息再投入，讓複利發揮作用"
}
```

- [ ] **Step 3: Commit**

```bash
git add bot/prompts/analysis.py bot/content/lessons.json
git commit -m "feat: analysis prompts and educational content"
```

---

## Task 8: handlers/menu.py and basic main.py

**Files:**
- Create: `bot/handlers/menu.py`
- Modify: `main.py`

- [ ] **Step 1: Create `bot/handlers/menu.py`**

```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📈 分析股票", callback_data="menu_analyze")],
        [InlineKeyboardButton("💰 個人理財教練", callback_data="menu_finance")],
        [InlineKeyboardButton("📚 學習投資知識", callback_data="menu_learn")],
    ]
    await update.message.reply_text(
        "嗨！我是你的投資助理 👋\n\n"
        "你可以直接輸入指令，或點選以下功能：\n\n"
        "• /analyze 2330 — 分析台積電\n"
        "• /analyze TSLA — 分析特斯拉\n"
        "• /finance — 個人理財教練\n"
        "• /learn ETF — 學習投資知識",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_analyze":
        await query.message.reply_text("請輸入股票代號：\n/analyze 2330\n/analyze TSLA")
    elif data == "menu_finance":
        await query.message.reply_text("輸入 /finance 開始個人理財教練")
    elif data == "menu_learn":
        await query.message.reply_text("輸入 /learn <主題>，例如：\n/learn ETF\n/learn 緊急備用金")
```

- [ ] **Step 2: Rewrite `main.py` to start the bot**

```python
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke test — start the bot locally**

Create a `.env` file from `.env.example` and fill in your real values. Then:

```bash
python main.py
```

Open Telegram, find your bot (from @BotFather), send `/start`.
Expected: bot replies with the welcome message and 3 buttons.

Stop the bot with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/menu.py main.py
git commit -m "feat: /start handler and main bot entry point"
```

---

## Task 9: handlers/analyze.py

**Files:**
- Create: `bot/handlers/analyze.py`
- Modify: `main.py`

- [ ] **Step 1: Create `bot/handlers/analyze.py`**

```python
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.services.stock import get_stock_summary
from bot.services.llm import call_llm, ANTHROPIC_ANALYSIS_MODEL
from bot.services.pdf import generate_pdf
from bot.prompts.analysis import PROMPTS, ANALYSIS_BUTTONS

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是一位華爾街資深股票分析師，用繁體中文撰寫專業且深入的分析報告。"
    "分析時引用提供的真實財務數據，結論要有邏輯依據，語氣客觀。"
)


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "請輸入股票代號，例如：\n/analyze 2330\n/analyze TSLA"
        )
        return

    ticker = context.args[0].upper().strip()
    context.user_data["analyze_ticker"] = ticker

    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"analyze_{key}")]
        for label, key in ANALYSIS_BUTTONS
    ]
    await update.message.reply_text(
        f"選擇 {ticker} 的分析類型：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def analyze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    analysis_key = query.data.replace("analyze_", "")
    ticker = context.user_data.get("analyze_ticker")

    if not ticker:
        await query.edit_message_text("請先使用 /analyze <代號> 指令")
        return

    label = next((l for l, k in ANALYSIS_BUTTONS if k == analysis_key), analysis_key)
    await query.edit_message_text(f"⏳ 正在分析 {ticker} — {label}，請稍候（約30秒）...")

    try:
        stock_data = await get_stock_summary(ticker)
        prompt = PROMPTS[analysis_key].format(ticker=ticker)
        user_msg = f"股票資料：\n{stock_data}\n\n{prompt}"

        # Run blocking LLM call in thread pool to avoid blocking the event loop
        content = await asyncio.to_thread(call_llm, _SYSTEM, user_msg, ANTHROPIC_ANALYSIS_MODEL)

        pdf_bytes = generate_pdf(ticker, label, content)

        await query.message.reply_document(
            document=pdf_bytes,
            filename=f"{ticker}_{analysis_key}_分析.pdf",
            caption=f"✅ {ticker} — {label} 分析完成",
        )
        await query.edit_message_text(f"✅ {ticker} {label} 分析完成")

    except Exception as exc:
        logger.error("Analysis failed for %s: %s", ticker, exc)
        await query.edit_message_text(f"❌ 分析失敗：{exc}")


def build_analyze_handler(auth_filter):
    return [
        CommandHandler("analyze", analyze_command, filters=auth_filter),
        CallbackQueryHandler(analyze_callback, pattern="^analyze_"),
    ]
```

- [ ] **Step 2: Update `main.py` to add analyze handlers**

Replace the `main()` function in `main.py`:

```python
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler
from bot.handlers.analyze import build_analyze_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    for handler in build_analyze_handler(auth):
        app.add_handler(handler)

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke test**

```bash
python main.py
```

In Telegram: send `/analyze 2330`
Expected: Bot shows 7 analysis type buttons.
Click "📊 完整分析".
Expected: Bot says "正在分析..." then sends a PDF file. Open the PDF and verify Chinese text renders correctly.

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/analyze.py main.py
git commit -m "feat: /analyze command with 7-button PDF analysis"
```

---

## Task 10: handlers/learn.py

**Files:**
- Create: `bot/handlers/learn.py`
- Modify: `main.py`

- [ ] **Step 1: Create `bot/handlers/learn.py`**

```python
import asyncio
import json
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.services.llm import call_llm, ANTHROPIC_CHAT_MODEL

logger = logging.getLogger(__name__)

_LESSONS_PATH = os.path.join(os.path.dirname(__file__), "..", "content", "lessons.json")
_SYSTEM = (
    "你是一位投資理財教育專家，用繁體中文為台灣完全新手解釋投資概念。"
    "語氣親切、易懂，避免行話，多舉台灣的實際例子。"
)


def _load_lessons() -> dict:
    with open(_LESSONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find_lesson(topic: str, lessons: dict) -> str | None:
    """Case-insensitive partial match against lesson keys."""
    topic_lower = topic.lower()
    for key, content in lessons.items():
        if key.lower() in topic_lower or topic_lower in key.lower():
            return content
    return None


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        lessons = _load_lessons()
        topic_list = "、".join(lessons.keys())
        await update.message.reply_text(
            f"📚 輸入你想學的主題，例如：\n"
            f"/learn ETF\n/learn 緊急備用金\n/learn 本益比\n\n"
            f"已有內容：{topic_list}\n\n"
            f"找不到的主題會由 AI 即時回答。"
        )
        return

    topic = " ".join(context.args)

    lessons = _load_lessons()
    lesson = _find_lesson(topic, lessons)

    if lesson:
        await update.message.reply_text(lesson)
        return

    # Fall back to Claude
    await update.message.reply_text(f"查詢「{topic}」中...")
    user_msg = (
        f"請用白話文解釋「{topic}」，包含：\n"
        f"1. 定義（一句話）\n2. 為什麼新手需要了解這個\n"
        f"3. 台灣實際例子\n4. 新手最需要知道的 1-2 件事\n\n長度約 300-400 字。"
    )

    try:
        response = await asyncio.to_thread(call_llm, _SYSTEM, user_msg, ANTHROPIC_CHAT_MODEL)
        await update.message.reply_text(response)
    except Exception as exc:
        logger.error("learn_command failed for topic '%s': %s", topic, exc)
        await update.message.reply_text(f"查詢失敗：{exc}")


def build_learn_handler(auth_filter):
    return CommandHandler("learn", learn_command, filters=auth_filter)
```

- [ ] **Step 2: Add learn handler to `main.py`**

```python
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler
from bot.handlers.analyze import build_analyze_handler
from bot.handlers.learn import build_learn_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    for handler in build_analyze_handler(auth):
        app.add_handler(handler)

    app.add_handler(build_learn_handler(auth))

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke test**

```bash
python main.py
```

In Telegram:
- Send `/learn ETF` → expect pre-written content (fast, no API call)
- Send `/learn 護城河是什麼` → expect Claude-generated response

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/learn.py main.py
git commit -m "feat: /learn command with pre-written lessons and Claude fallback"
```

---

## Task 11: handlers/finance.py (Personal Finance Coach)

**Files:**
- Create: `bot/handlers/finance.py`
- Modify: `main.py`

- [ ] **Step 1: Create `bot/handlers/finance.py`**

```python
import asyncio
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
)

from bot.services.github_store import read_profile, write_profile
from bot.services.llm import call_llm, ANTHROPIC_CHAT_MODEL

logger = logging.getLogger(__name__)

INCOME, EXPENSES, SAVINGS, DEBT, GOAL = range(5)

_GOALS = [
    ("🏦 緊急備用金", "emergency_fund"),
    ("📈 開始投資ETF", "start_etf"),
    ("💰 存第一桶金", "first_million"),
    ("🏠 買房計畫", "buy_house"),
    ("🌅 退休規劃", "retirement"),
]

_GOAL_LABELS = {k: l for l, k in _GOALS}

_SYSTEM = (
    "你是一位專業的個人理財教練，專門幫助台灣的投資新手規劃財務。"
    "請用繁體中文給出具體可執行的建議，語氣鼓勵且實際。"
    "提供具體的金額、時間和行動步驟，讓完全沒有理財經驗的人也能照著做。"
)


async def finance_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    existing = await asyncio.to_thread(read_profile)

    if existing and existing.get("monthly_income"):
        keyboard = [
            [InlineKeyboardButton("✅ 使用現有資料繼續", callback_data="finance_use_existing")],
            [InlineKeyboardButton("🔄 重新設定", callback_data="finance_reset")],
        ]
        await update.message.reply_text(
            f"找到你上次的資料（{existing.get('updated_at', '')}）：\n"
            f"月收入：NT${existing.get('monthly_income', 0):,}\n"
            f"目標：{existing.get('goal', '未設定')}\n\n要繼續還是重新設定？",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        context.user_data["existing_profile"] = existing
        return GOAL

    await update.message.reply_text(
        "歡迎使用個人理財教練！💪\n\n"
        "我會問你幾個問題，然後給你專屬的薪水分配建議。\n\n"
        "第一步：請輸入你每月**稅後**收入（新台幣，只要數字）："
    )
    return INCOME


async def _handle_existing_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "finance_reset":
        await query.edit_message_text("好的，重新開始！\n\n請輸入你每月稅後收入（新台幣）：")
        context.user_data.pop("existing_profile", None)
        return INCOME

    # Use existing — go straight to goal selection
    existing = context.user_data.get("existing_profile", {})
    context.user_data.update({
        "income": existing.get("monthly_income", 0),
        "expenses": existing.get("monthly_expenses", 0),
        "savings": existing.get("savings", 0),
        "debt": existing.get("debt", 0),
    })
    keyboard = [[InlineKeyboardButton(l, callback_data=f"goal_{k}")] for l, k in _GOALS]
    await query.edit_message_text(
        "你想更新理財目標嗎？選一個：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return GOAL


def _parse_number(text: str) -> int | None:
    try:
        return int(text.replace(",", "").replace("，", "").replace(" ", ""))
    except ValueError:
        return None


async def got_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，例如：50000")
        return INCOME
    context.user_data["income"] = n
    await update.message.reply_text("每月固定支出大約多少？（房租、水電、交通、伙食，新台幣）：")
    return EXPENSES


async def got_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，例如：20000")
        return EXPENSES
    context.user_data["expenses"] = n
    await update.message.reply_text("目前有多少存款？（新台幣，沒有請輸入 0）：")
    return SAVINGS


async def got_savings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，沒有存款請輸入 0")
        return SAVINGS
    context.user_data["savings"] = n
    await update.message.reply_text("有任何貸款或負債嗎？（沒有請輸入 0，新台幣）：")
    return DEBT


async def got_debt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，沒有負債請輸入 0")
        return DEBT
    context.user_data["debt"] = n
    keyboard = [[InlineKeyboardButton(l, callback_data=f"goal_{k}")] for l, k in _GOALS]
    await update.message.reply_text(
        "最後一步！你最想達成哪個理財目標？",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return GOAL


async def got_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    goal_key = query.data.replace("goal_", "")
    goal_label = _GOAL_LABELS.get(goal_key, goal_key)

    profile = {
        "monthly_income": context.user_data.get("income", 0),
        "monthly_expenses": context.user_data.get("expenses", 0),
        "savings": context.user_data.get("savings", 0),
        "debt": context.user_data.get("debt", 0),
        "goal": goal_label,
        "updated_at": str(date.today()),
    }

    await asyncio.to_thread(write_profile, profile)
    await query.edit_message_text(f"目標：{goal_label} ✅\n\n正在為你生成個人化理財建議...")

    disposable = profile["monthly_income"] - profile["monthly_expenses"]
    user_msg = (
        f"根據以下財務狀況，請給出個人化的薪水分配建議和理財計畫：\n\n"
        f"每月稅後收入：NT${profile['monthly_income']:,}\n"
        f"每月固定支出：NT${profile['monthly_expenses']:,}\n"
        f"每月可支配餘額：NT${disposable:,}\n"
        f"目前存款：NT${profile['savings']:,}\n"
        f"負債：NT${profile['debt']:,}\n"
        f"理財目標：{profile['goal']}\n\n"
        f"請提供：\n"
        f"1. 建議的薪水分配比例（根據他的實際數字客製化，附具體金額）\n"
        f"2. 針對「{profile['goal']}」的第一步具體行動（本週就能做到的事）\n"
        f"3. 預估達成目標的時間\n"
        f"4. 給完全新手最重要的 2 個提醒"
    )

    try:
        advice = await asyncio.to_thread(call_llm, _SYSTEM, user_msg, ANTHROPIC_CHAT_MODEL)
        await query.message.reply_text(advice)
    except Exception as exc:
        logger.error("Finance advice generation failed: %s", exc)
        await query.message.reply_text(f"建議生成失敗：{exc}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("已取消。輸入 /finance 可以重新開始。")
    return ConversationHandler.END


def build_finance_handler(auth_filter):
    return ConversationHandler(
        entry_points=[CommandHandler("finance", finance_start, filters=auth_filter)],
        states={
            INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_income)],
            EXPENSES: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expenses)],
            SAVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_savings)],
            DEBT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_debt)],
            GOAL: [
                CallbackQueryHandler(got_goal, pattern="^goal_"),
                CallbackQueryHandler(_handle_existing_choice, pattern="^finance_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
```

- [ ] **Step 2: Add finance handler to `main.py`**

```python
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.auth import build_auth_filter
from bot.handlers.menu import start_handler, menu_callback_handler
from bot.handlers.analyze import build_analyze_handler
from bot.handlers.learn import build_learn_handler
from bot.handlers.finance import build_finance_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def main() -> None:
    auth = build_auth_filter()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler, filters=auth))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))

    for handler in build_analyze_handler(auth):
        app.add_handler(handler)

    app.add_handler(build_learn_handler(auth))
    app.add_handler(build_finance_handler(auth))

    logging.getLogger(__name__).info("Bot started, polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke test the full finance flow**

Prerequisites: set up a real GitHub private repo named `stock-bot-data` with no files yet, and fill `.env` with real `GITHUB_TOKEN` and `GITHUB_REPO`.

```bash
python main.py
```

In Telegram:
1. Send `/finance`
2. Enter income: `50000`
3. Enter expenses: `20000`
4. Enter savings: `100000`
5. Enter debt: `0`
6. Click "🏦 緊急備用金"

Expected: Bot generates and sends a personalized finance plan. Check GitHub repo — `profile.json` should appear.

Send `/finance` again → bot should show existing profile with "使用現有資料" option.

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/finance.py main.py
git commit -m "feat: /finance personal finance coach with ConversationHandler"
```

---

## Task 12: render.yaml and deployment

**Files:**
- Create: `render.yaml`
- Create: `.gitignore`

- [ ] **Step 1: Create `.gitignore`**

```
.env
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
dist/
build/
*.otf
*.ttc
```

Note: `*.otf` and `*.ttc` exclude the downloaded font from git (too large). The font is downloaded during deployment build.

- [ ] **Step 2: Create `render.yaml`**

```yaml
services:
  - type: worker
    name: stock-telegram-bot
    runtime: python
    buildCommand: pip install -r requirements.txt && python scripts/download_font.py
    startCommand: python main.py
    envVars:
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: GITHUB_TOKEN
        sync: false
      - key: GITHUB_REPO
        sync: false
      - key: LLM_PROVIDER
        value: anthropic
      - key: ALLOWED_TELEGRAM_ID
        sync: false
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit everything**

```bash
git add render.yaml .gitignore
git commit -m "feat: render.yaml deployment config"
```

- [ ] **Step 5: Deploy to Render**

1. Push repo to GitHub: `git remote add origin <your-repo-url> && git push -u origin main`
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo
4. Render detects `render.yaml` automatically
5. In the Environment tab, set the 5 secret env vars (`sync: false` ones)
6. Click Deploy

Expected: Build log shows pip install + font download, then `Bot started, polling...`. Send `/start` from Telegram to verify the deployed bot responds.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup before deploy"
git push origin main
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task that covers it |
|---|---|
| Telegram Bot wrapping existing logic | Tasks 8-11 |
| /analyze 0050, /analyze TSLA | Task 9 |
| 7 Wall Street prompts → PDF | Tasks 7, 9 |
| PDF sent via Telegram | Task 9 |
| Personal finance coach (3-stage dialogue) | Task 11 |
| /learn with pre-written + Claude fallback | Task 10 |
| GitHub JSON user profile storage | Task 3 |
| Single-user auth (Telegram ID whitelist) | Task 2 |
| Claude + gpt-4o-mini switchable | Task 5 |
| Render deployment (24/7) | Task 12 |
| Font download for CJK PDF | Task 6 |

**Placeholder scan:** No TBDs found. All code blocks are complete.

**Type consistency check:**
- `call_llm(system, user, model)` — consistent across Tasks 5, 9, 10, 11
- `generate_pdf(ticker, analysis_type, content)` → `bytes` — consistent Tasks 6, 9
- `read_profile()` → `dict`, `write_profile(dict)` — consistent Tasks 3, 11
- `get_stock_summary(ticker)` → `dict` (async) — consistent Tasks 4, 9
- `build_auth_filter()` → `tg_filters.User` — consistent Tasks 2, 8, 9, 10, 11

All types match. ✅
