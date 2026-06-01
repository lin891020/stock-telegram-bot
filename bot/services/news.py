import asyncio
import logging
import re
from datetime import date
import yfinance as yf

from bot.services.llm import call_llm
from bot.services.stock import is_taiwan_stock, get_stock_summary

logger = logging.getLogger(__name__)


def _format_price(stock_data: dict) -> str:
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
    yf_ticker = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker
    try:
        stock = yf.Ticker(yf_ticker)
        raw = stock.news or []
        headlines = []
        for item in raw[:5]:
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


def _parse_llm_sections(text: str, tickers: list[str]) -> dict[str, str]:
    """Parse LLM output into {ticker: analysis} by [TICKER] markers."""
    result = {}
    pattern = re.compile(r"\[([A-Z0-9]+)\]", re.IGNORECASE)
    parts = pattern.split(text)
    # parts = [preamble, ticker1, body1, ticker2, body2, ...]
    i = 1
    while i + 1 < len(parts):
        t = parts[i].upper().strip()
        body = parts[i + 1].strip()
        if t in [x.upper() for x in tickers]:
            result[t] = body
        i += 2
    return result


async def fetch_and_summarize(tickers: list[str]) -> str:
    news_block_task = asyncio.to_thread(_build_news_block, tickers)
    price_tasks = [get_stock_summary(t) for t in tickers]

    news_block, *price_results = await asyncio.gather(news_block_task, *price_tasks)
    prices = {t: data for t, data in zip(tickers, price_results)}

    today = date.today().strftime("%Y/%m/%d")

    # LLM only writes analysis — no prices
    system = "你是一位專業股票研究員。根據提供的新聞標題，為每支股票寫簡短分析。用繁體中文，語氣簡潔專業。"
    user = f"""今天日期：{today}

以下是各股票的最新新聞標題。請針對每支股票寫 2-3 句新聞摘要，最後一行標出影響方向。
若無新聞則只輸出「（本日無相關新聞）」。

輸出規則：
- 每支股票以 [代號] 開頭（例如 [2408]、[MU]）
- 純文字，不要使用 # ## ** 等符號
- 影響方向用：▲ 正面 / ▼ 負面 / ● 中性

{news_block}"""

    llm_output = await asyncio.to_thread(call_llm, system, user)
    sections = _parse_llm_sections(llm_output, tickers)

    # Assemble final output: Python formats price, LLM provides analysis
    output_parts = []
    for t in tickers:
        data = prices.get(t, {})
        name = data.get("name", "") if isinstance(data, dict) else ""
        label = f"{name}({t})" if name and name != t else t
        price_line = _format_price(data) if isinstance(data, dict) and not data.get("error") else ""
        analysis = sections.get(t.upper(), "（無資料）")

        block = label
        if price_line:
            block += f"\n\n{price_line}"
        block += f"\n\n{analysis}"
        output_parts.append(block)

    header = f"晨報 {today}" if len(tickers) > 1 else ""
    body = "\n\n---\n\n".join(output_parts)
    return f"{header}\n\n{body}" if header else body
