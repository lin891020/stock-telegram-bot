import re
import asyncio
import httpx
import yfinance as yf
from datetime import date, timedelta

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
_MONTHS_TO_FETCH = 3
_MAX_RETRIES = 3

def is_taiwan_stock(ticker: str) -> bool:
    """Return True if ticker looks like a Taiwan stock code (4-6 digits)."""
    return bool(re.match(r'^\d{4,6}$', ticker.strip()))


def looks_like_ticker(query: str) -> bool:
    """Return True if the query looks like a direct ticker symbol (not a company name)."""
    q = query.strip().upper()
    return bool(re.match(r'^\d{4,6}$', q) or re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', q))


def search_ticker(query: str, max_results: int = 4) -> list[dict]:
    """Search for stocks by company name. Returns list of {symbol, name, exchange}."""
    try:
        results = yf.Search(query, max_results=max_results)
        return [
            {
                "symbol": q.get("symbol", ""),
                "name": q.get("longname") or q.get("shortname") or q.get("symbol", ""),
                "exchange": q.get("exchange", ""),
            }
            for q in results.quotes
            if q.get("symbol")
        ][:max_results]
    except Exception:
        return []

def fetch_us_data(ticker: str) -> dict:
    """Fetch financial summary for a US stock using yfinance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as e:
        return {"ticker": ticker, "error": f"查無股票代號 {ticker}（{e}）", "market": "US"}

    if not info or info.get("trailingPegRatio") is None and info.get("currentPrice") is None and info.get("regularMarketPrice") is None and info.get("longName") is None:
        return {"ticker": ticker, "error": f"查無股票代號 {ticker}，請確認 ticker 是否正確（例如 Micron → MU）", "market": "US"}

    return {
        "ticker": ticker,
        "name": info.get("longName", ticker),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "prev_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
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

def _months_to_query(reference: date) -> list:
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

    all_rows = [row for monthly in reversed(results) for row in monthly]
    if not all_rows:
        return {"ticker": ticker, "error": f"查無股票代號 {ticker}", "market": "TW"}

    latest = all_rows[-1]
    prev = all_rows[-2] if len(all_rows) >= 2 else None
    close = latest[6].replace(",", "") if len(latest) > 6 else "N/A"
    prev_close_raw = prev[6].replace(",", "") if prev and len(prev) > 6 else "N/A"
    volume = latest[1].replace(",", "") if len(latest) > 1 else "N/A"

    name = ticker
    try:
        info = yf.Ticker(f"{ticker}.TW").info
        name = info.get("shortName") or info.get("longName") or ticker
    except Exception:
        pass

    return {
        "ticker": ticker,
        "name": name,
        "date": _roc_to_ad(latest[0]),
        "close": float(close) if close != "N/A" else None,
        "prev_close": float(prev_close_raw) if prev_close_raw != "N/A" else None,
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
