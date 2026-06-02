import asyncio
import html
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


def _fetch_news(ticker: str) -> list[dict]:
    """Return up to 5 news items as [{title, url}]."""
    yf_ticker = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker
    try:
        stock = yf.Ticker(yf_ticker)
        raw = stock.news or []
        items = []
        for item in raw[:5]:
            content = item.get("content", {})
            if isinstance(content, dict):
                title = content.get("title") or item.get("title", "")
                url = (
                    (content.get("canonicalUrl") or {}).get("url")
                    or (content.get("clickThroughUrl") or {}).get("url")
                    or item.get("link", "")
                )
            else:
                title = item.get("title", "")
                url = item.get("link", "")
            if title:
                items.append({"title": title, "url": url})
        return items
    except Exception as e:
        logger.warning("News fetch failed for %s: %s", ticker, e)
        return []


def _build_news_data(tickers: list[str]) -> tuple[str, dict]:
    """Returns (headlines_block_for_llm, news_items_dict {ticker: [{title, url}]})."""
    blocks = []
    news_items = {}
    for ticker in tickers:
        items = _fetch_news(ticker)
        news_items[ticker] = items
        if not items:
            blocks.append(f"=== {ticker} ===\n（無新聞）")
        else:
            lines = "\n".join(f"- {i['title']}" for i in items)
            blocks.append(f"=== {ticker} ===\n{lines}")
    return "\n\n".join(blocks), news_items


def _parse_llm_sections(text: str, tickers: list[str]) -> dict[str, str]:
    pattern = re.compile(r"\[([A-Z0-9]+)\]", re.IGNORECASE)
    parts = pattern.split(text)
    result = {}
    i = 1
    while i + 1 < len(parts):
        t = parts[i].upper().strip()
        body = parts[i + 1].strip()
        if t in [x.upper() for x in tickers]:
            result[t] = body
        i += 2
    return result


async def fetch_and_summarize(tickers: list[str]) -> str:
    news_data_task = asyncio.to_thread(_build_news_data, tickers)
    price_tasks = [get_stock_summary(t) for t in tickers]

    (news_block, news_items), *price_results = await asyncio.gather(news_data_task, *price_tasks)
    prices = {t: data for t, data in zip(tickers, price_results)}

    today = date.today().strftime("%Y/%m/%d")

    system = "你是一位專業股票研究員。根據提供的新聞標題，為每支股票寫簡短分析。用繁體中文，語氣簡潔專業。"
    user = f"""今天日期：{today}

以下是各股票的最新新聞標題。請針對每支股票寫 2-3 句新聞摘要，最後一行標出影響方向。
若無新聞則只輸出「（本日無相關新聞）」。

輸出規則：
- 每支股票以 [代號] 開頭（例如 [2408]、[MU]）
- 純文字，不要使用 # ## ** 等符號
- 影響方向用：▲ 正面 / ▼ 負面 / ● 中性
- 只分析該股票本身，不要提及其他公司名稱
- 若新聞內容與該股票無直接關聯，輸出「（本日無直接相關新聞）」

{news_block}"""

    llm_output = await asyncio.to_thread(call_llm, system, user)
    sections = _parse_llm_sections(llm_output, tickers)

    output_parts = []
    for t in tickers:
        data = prices.get(t, {})
        name = data.get("name", "") if isinstance(data, dict) else ""
        label = f"{name}({t})" if name and name != t else t
        price_line = _format_price(data) if isinstance(data, dict) and not data.get("error") else ""
        analysis = sections.get(t.upper(), "（無資料）")

        block = html.escape(label)
        if price_line:
            block += f"\n\n{html.escape(price_line)}"
        block += f"\n\n{html.escape(analysis)}"

        items_with_url = [i for i in news_items.get(t, []) if i.get("url")]
        if items_with_url:
            links = "\n".join(
                f'• <a href="{html.escape(i["url"])}">{html.escape(i["title"][:55])}{"…" if len(i["title"]) > 55 else ""}</a>'
                for i in items_with_url[:3]
            )
            block += f"\n\nSource:\n{links}"

        output_parts.append(block)

    header = html.escape(f"晨報 {today}")
    body = "\n\n---\n\n".join(output_parts)
    return f"{header}\n\n{body}"
