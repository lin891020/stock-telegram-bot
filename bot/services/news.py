import asyncio
import logging
from datetime import date
import yfinance as yf

from bot.services.llm import call_llm
from bot.services.stock import is_taiwan_stock, get_stock_summary

logger = logging.getLogger(__name__)


def _format_price(stock_data: dict) -> str:
    """Format price line: 收 980.0 元  ▲ +2.30%（+22.0）"""
    price = stock_data.get("price") or stock_data.get("close")
    prev = stock_data.get("prev_close")
    currency = "元" if stock_data.get("market") == "TW" else "USD"

    if not price:
        return ""

    if prev and prev != 0:
        change = price - prev
        pct = change / prev * 100
        arrow = "▲" if change >= 0 else "▼"
        sign = "+" if change >= 0 else ""
        return f"收 {price:.2f} {currency}  {arrow} {sign}{pct:.2f}%（{sign}{change:.2f}）"

    return f"收 {price:.2f} {currency}"


def _fetch_news(ticker: str) -> list[str]:
    """Return up to 5 news headlines for a ticker."""
    yf_ticker = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker
    try:
        stock = yf.Ticker(yf_ticker)
        raw = stock.news or []
        headlines = []
        for item in raw[:5]:
            # yfinance ≥1.4 wraps content in a nested dict
            content = item.get("content", {})
            if isinstance(content, dict):
                title = content.get("title") or item.get("title", "")
            else:
                title = item.get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        logger.warning("News fetch failed for %s: %s", ticker, e)
        return []


def _build_news_block(tickers: list[str]) -> str:
    blocks = []
    for ticker in tickers:
        headlines = _fetch_news(ticker)
        if not headlines:
            blocks.append(f"=== {ticker} ===\n（無新聞）")
        else:
            lines = "\n".join(f"- {h}" for h in headlines)
            blocks.append(f"=== {ticker} ===\n{lines}")
    return "\n\n".join(blocks)


async def fetch_and_summarize(tickers: list[str]) -> str:
    news_block_task = asyncio.to_thread(_build_news_block, tickers)
    price_tasks = [get_stock_summary(t) for t in tickers]

    news_block, *price_results = await asyncio.gather(news_block_task, *price_tasks)
    prices = {t: data for t, data in zip(tickers, price_results)}

    today = date.today().strftime("%Y/%m/%d")

    # Build price header block to prepend to LLM prompt
    price_lines = []
    for t in tickers:
        data = prices.get(t, {})
        if not isinstance(data, dict) or data.get("error"):
            continue
        line = _format_price(data)
        if line:
            price_lines.append(f"{t}: {line}")
    price_block = "\n".join(price_lines)

    system = "你是一位專業股票研究員，每天早上為投資人撰寫追蹤股票晨報。用繁體中文，語氣簡潔專業。"
    user = f"""今天日期：{today}

【股價資料】
{price_block}

【最新新聞標題】
{news_block}

請針對每支有新聞的股票：
1. 第一行顯示股價資料（直接從上方【股價資料】複製，不要改動數字）
2. 用 2-3 句話總結新聞重點
3. 標出對股價的影響方向：正面 / 負面 / 中性
4. 若無新聞則只顯示股價，不需寫新聞摘要

輸出格式規則（必須遵守）：
- 純文字，不要使用 # ## ### 標題符號
- 不要使用 ** 粗體符號
- 每支股票格式如下（注意空行）：

股票代號 公司名
（空行）
收 xxx 元/USD  ▲/▼ +x.xx%（+xx.xx）
（空行）
新聞摘要 2-3 句
▲ 正面 / ▼ 負面 / ● 中性

- 每支股票之間用「---」分隔"""

    return await asyncio.to_thread(call_llm, system, user)
