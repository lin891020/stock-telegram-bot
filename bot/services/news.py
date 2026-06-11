import asyncio
import html
import logging
import re
import time
from datetime import date, datetime, timezone
import yfinance as yf

from bot.services.llm import call_llm
from bot.services.stock import is_taiwan_stock, get_stock_summary
logger = logging.getLogger(__name__)


# 單日漲跌幅絕對值達此門檻視為「大事」，會進重點分析區
_BIG_MOVE_PCT = 3.0


def _day_pct(stock_data: dict):
    """單日漲跌幅（%），無資料回 None。"""
    if not isinstance(stock_data, dict) or stock_data.get("error"):
        return None
    price = stock_data.get("price") or stock_data.get("close")
    prev = stock_data.get("prev_close")
    if not price or not prev:
        return None
    return (price - prev) / prev * 100


def _price_line(ticker: str, stock_data: dict) -> str:
    name = stock_data.get("name", "") if isinstance(stock_data, dict) else ""
    label = f"{name}({ticker})" if name and name != ticker else ticker
    price = stock_data.get("price") or stock_data.get("close") if isinstance(stock_data, dict) else None
    if not price:
        return f"{label}  無報價"
    pct = _day_pct(stock_data)
    if pct is None:
        return f"{label}  {price:,.2f}"
    arrow = "▲" if pct >= 0 else "▼"
    sign = "+" if pct >= 0 else ""
    warn = " ⚠️" if abs(pct) >= _BIG_MOVE_PCT else ""
    return f"{label}  {price:,.2f}  {arrow} {sign}{pct:.2f}%{warn}"


_48H = 48 * 3600


def _is_fresh(item: dict) -> bool:
    """Return True if the news article was published within the last 48 hours."""
    content = item.get("content", {})
    # Try ISO pubDate from content dict first
    pub_date_str = content.get("pubDate") if isinstance(content, dict) else None
    if pub_date_str:
        try:
            pub_dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - pub_dt).total_seconds() < _48H
        except ValueError:
            pass
    # Fall back to Unix timestamp at top level
    pts = item.get("providerPublishTime")
    if pts:
        return (time.time() - float(pts)) < _48H
    return True  # unknown age → keep


def _fetch_news(ticker: str) -> list[dict]:
    """Return up to 5 fresh (< 48 h) news items as [{title, url}]."""
    yf_ticker = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker
    try:
        stock = yf.Ticker(yf_ticker)
        raw = stock.news or []
        items = []
        for item in raw:
            if not _is_fresh(item):
                continue
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
            if len(items) >= 5:
                break
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
    # Allow dots for tickers like BRK.B
    pattern = re.compile(r"\[([A-Z0-9.]+)\]", re.IGNORECASE)
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
    """自選股快報（HTML）：行情總覽（異動排前）→ 重點分析（有新聞或大漲跌）→ 無大事收合。"""
    news_data_task = asyncio.to_thread(_build_news_data, tickers)
    price_tasks = [get_stock_summary(t) for t in tickers]

    (_, news_items), *price_results = await asyncio.gather(news_data_task, *price_tasks)
    prices = {t: data for t, data in zip(tickers, price_results)}

    def _sort_key(t: str):
        pct = _day_pct(prices.get(t, {}))
        return -abs(pct) if pct is not None else 0.0

    ordered = sorted(tickers, key=_sort_key)

    def _label(t: str) -> str:
        data = prices.get(t, {})
        name = data.get("name", "") if isinstance(data, dict) else ""
        return f"{name}({t})" if name and name != t else t

    # 有新聞或單日漲跌 >= 3% 才進重點分析；其餘收合成一行
    active = [
        t for t in ordered
        if news_items.get(t) or abs(_day_pct(prices.get(t, {})) or 0) >= _BIG_MOVE_PCT
    ]
    quiet = [t for t in ordered if t not in active]

    parts = []

    price_block = "\n".join(_price_line(t, prices.get(t, {})) for t in ordered)
    parts.append(f"💼 自選股行情\n{html.escape(price_block)}")

    if active:
        today = date.today().strftime("%Y/%m/%d")
        news_block = "\n\n".join(
            f"=== {t} ===\n" + (
                "\n".join(f"- {i['title']}" for i in news_items[t]) if news_items.get(t) else "（無新聞）"
            )
            for t in active
        )
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
        sections = _parse_llm_sections(llm_output, active)

        analysis_parts = []
        for t in active:
            analysis = sections.get(t.upper(), "（無資料）")
            block = f"<b>{html.escape(_label(t))}</b>\n{html.escape(analysis)}"
            items_with_url = [i for i in news_items.get(t, []) if i.get("url")]
            if items_with_url:
                links = "\n".join(
                    f'• <a href="{html.escape(i["url"])}">{html.escape(i["title"][:55])}{"…" if len(i["title"]) > 55 else ""}</a>'
                    for i in items_with_url[:3]
                )
                block += f"\n{links}"
            analysis_parts.append(block)
        parts.append("📌 重點分析\n\n" + "\n\n".join(analysis_parts))

    if quiet:
        quiet_labels = "、".join(_label(t) for t in quiet)
        parts.append(html.escape(f"😴 無大事：{quiet_labels}"))

    return "\n\n".join(parts)
