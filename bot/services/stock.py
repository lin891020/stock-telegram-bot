import asyncio
import logging
import re
import httpx
import yfinance as yf
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_CORP_SUFFIX = re.compile(
    r",?\s*(Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|Co\.?|Holdings?|Group|PLC|S\.A\.?|N\.V\.?)\.?\s*$",
    re.IGNORECASE,
)

def clean_us_name(name: str) -> str:
    """Strip corporate suffixes: 'NVIDIA Corporation' → 'NVIDIA'."""
    return _CORP_SUFFIX.sub("", name).strip()

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

    raw_name = info.get("shortName") or info.get("longName") or ticker
    return {
        "ticker": ticker,
        "name": clean_us_name(raw_name),
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
        # ValueError 是為了 JSONDecodeError：TWSE 忙的時候會回 HTTP 200
        # 但內容是 HTML 錯誤頁，resp.json() 就炸了。它不是 httpx 的例外，
        # 以前漏在這個 except 外面——於是不但沒重試，還一路往上炸掉整張
        # 股票卡片（實測按 2454 的按鈕收到 JSONDecodeError traceback）。
        # 而且五個月份是 gather 併發抓的，一個月壞掉就全毀。
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            if attempt == _MAX_RETRIES - 1:
                logger.warning(
                    "TWSE %s %s 連續 %d 次失敗：%s: %s",
                    stock_no, query_date, _MAX_RETRIES, type(e).__name__, e,
                )
                return []
            await asyncio.sleep(2 ** attempt)
    return []

def _intraday_sync(ticker: str) -> tuple:
    """(現價, 前收) 或 (None, None)。台股含上櫃 fallback。

    跟 get_stock_summary 的差別是**時效**：台股報價走 TWSE 盤後結算，
    盤中查到的是前一個交易日的收盤；這裡走 yfinance 的日線，盤中的
    最後一列就是即時價。價格提醒、漲跌停偵測、盤中速報都用這條。

    ⚠️ 不要改回 fast_info.previous_close——它會給錯的前收。實測 2026-09-01：

        台積電  fast_info 說 2,395（那是當天開盤價）  正確是 2,405
        南亞科  fast_info 說   549（什麼都不是）      正確是   543
        聯發科  fast_info 說 3,925  ✓ 剛好對

    前收是漲跌停價與 ±5% 提醒的分母，錯了會漏報或誤報。日線的倒數第二列
    才是可靠的，而且實測還比 fast_info 快（16ms vs 39ms）。
    """
    symbols = [f"{ticker}.TW", f"{ticker}.TWO"] if is_taiwan_stock(ticker) else [ticker]
    for symbol in symbols:
        try:
            closes = yf.Ticker(symbol).history(period="5d")["Close"].dropna()
            if len(closes) >= 2:
                return float(closes.iloc[-1]), float(closes.iloc[-2])
            if len(closes) == 1:
                return float(closes.iloc[-1]), None
        except Exception:
            continue
    logger.warning("intraday quote failed for %s", ticker)
    return None, None


async def intraday_quote(ticker: str) -> tuple:
    return await asyncio.to_thread(_intraday_sync, ticker)


def _fetch_tw_via_yf(ticker: str) -> dict:
    """上櫃股票不在 TWSE 上市 API，fallback 到 yfinance（.TWO 上櫃 / .TW 上市）。"""
    from bot.services.tw_stocks import get_tw_name
    for suffix in (".TWO", ".TW"):
        try:
            stock = yf.Ticker(f"{ticker}{suffix}")
            info = stock.fast_info
            price = info.last_price
            if not price:
                continue
            prev = info.previous_close
            name = get_tw_name(ticker)
            if not name:
                try:
                    name = stock.info.get("shortName") or stock.info.get("longName") or ticker
                except Exception:
                    name = ticker
            return {
                "ticker": ticker,
                "name": name,
                "close": float(price),
                "prev_close": float(prev) if prev else None,
                "market": "TW",
            }
        except Exception:
            continue
    return {"ticker": ticker, "error": f"查無股票代號 {ticker}", "market": "TW"}


async def fetch_taiwan_data(ticker: str) -> dict:
    """Fetch recent price data for a Taiwan stock from TWSE."""
    query_dates = _months_to_query(date.today())
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch_month(client, ticker, d) for d in query_dates])

    all_rows = [row for monthly in reversed(results) for row in monthly]
    if not all_rows:
        # TWSE 只有上市股票；上櫃（如 5274）改走 yfinance
        return await asyncio.to_thread(_fetch_tw_via_yf, ticker)

    latest = all_rows[-1]
    prev = all_rows[-2] if len(all_rows) >= 2 else None
    close = latest[6].replace(",", "") if len(latest) > 6 else "N/A"
    prev_close_raw = prev[6].replace(",", "") if prev and len(prev) > 6 else "N/A"
    volume = latest[1].replace(",", "") if len(latest) > 1 else "N/A"

    from bot.services.tw_stocks import get_tw_name
    name = get_tw_name(ticker) or ticker

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
    # fetch_us_data 是同步的 yfinance 呼叫（.info 是最慢的那個，約 1-3 秒）。
    # 直接 await 會卡住整個 event loop：呼叫端常用 gather 一次抓好幾支，
    # 沒包 to_thread 的話那個 gather 是假的——實際是一支一支輪流跑，
    # 而且期間整隻 bot 對所有人沒反應。
    return await asyncio.to_thread(fetch_us_data, ticker)
