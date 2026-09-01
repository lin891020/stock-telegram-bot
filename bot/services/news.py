import asyncio
import html
import logging
import re
import time
from datetime import datetime, timezone
import yfinance as yf

from bot.services.big_moves import classify_move
from bot.services.formatting import label, price_with_change
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
    """晨報的一行報價。

    格式走 formatting.price_with_change，跟 /price、卡片、收盤速報、
    提醒推播同一份——晨報以前自己寫了一份（沒有單位、沒有絕對漲跌），
    於是同一支股票早上跟下午長得不一樣。
    """
    lbl = label(ticker, stock_data)
    if not isinstance(stock_data, dict):
        return f"{lbl}  無報價"
    price = stock_data.get("price") or stock_data.get("close")
    if not price:
        return f"{lbl}  無報價"
    pct = _day_pct(stock_data)
    warn = " ⚠️" if pct is not None and abs(pct) >= _BIG_MOVE_PCT else ""
    body = price_with_change(price, stock_data.get("prev_close"), stock_data.get("market"))
    return f"{lbl}  {body}{warn}"


def _tw_as_of(tw: list[str], prices: dict) -> str:
    """台股區塊的資料日期，例如「（8/28 收盤）」。

    晨報這一行是每天都會看的東西，卻是整個 bot 裡最含糊的地方——
    台股走 TWSE 盤後結算，這裡卻只印一個裸數字，看起來跟旁邊接近
    即時的美股一模一樣。日期掛在區塊標題上，比每行都掛更省版面。
    """
    stamps = {
        (prices.get(t, {}).get("date") or "")[:10].replace("-", "/")
        for t in tw
    }
    stamps = {s for s in stamps if len(s) == 10}
    if len(stamps) != 1:
        return ""
    stamp = stamps.pop()
    return f"（{int(stamp[5:7])}/{int(stamp[8:10])} 收盤）"


def _price_overview(tw: list[str], us: list[str], prices: dict) -> str:
    """行情總覽：台股、美股分兩區塊。只有單一市場時不加標題（避免多餘的一行）。"""
    groups = [(f"🇹🇼 台股{_tw_as_of(tw, prices)}", tw), ("🇺🇸 美股", us)]
    show_headers = bool(tw) and bool(us)

    sections = []
    for header, tickers in groups:
        if not tickers:
            continue
        lines = "\n".join(_price_line(t, prices.get(t, {})) for t in tickers)
        sections.append(f"{header}\n{html.escape(lines)}" if show_headers else html.escape(lines))

    return "💼 自選股行情\n\n" + "\n\n".join(sections)


def _headline_block(ticker: str, label_text: str, items: list[dict]) -> str:
    """一支股票的新聞標題與連結。

    刻意不做 AI 摘要。新聞是整個系統裡唯一沒有證據包紀律的路徑——
    模型拿到的是裸標題，寫出來的句子無從溯源，實測連續出過兩種幻覺：
    把 NVIDIA 的內容寫成台積電的、把 Druckenmiller 說成巴菲特的人。
    三個標題自己掃兩秒就懂，模型的加值抵不過它編造的風險。
    """
    head = f"<b>{html.escape(label_text)}</b>"
    if not items:
        return f"{head}\n（本日無相關新聞）"
    lines = []
    for item in items[:4]:
        title = html.escape(item["title"][:80])
        url = item.get("url")
        lines.append(f'• <a href="{html.escape(url)}">{title}</a>' if url else f"• {title}")
    return head + "\n" + "\n".join(lines)


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


# 公司名稱裡不具識別度的字，不拿來當比對詞
_GENERIC = {
    "the", "and", "inc", "ltd", "llc", "plc", "corp", "corporation", "company",
    "limited", "holdings", "holding", "group", "technologies", "technology",
    "international", "industries", "electronics", "co",
}


def _match_terms(ticker: str, name: str) -> set[str]:
    """判斷一則標題是否真的在講這家公司時，可接受的比對詞。

    包含代號、公司名的實詞，以及首字母縮寫——yfinance 的標題寫
    「TSMC」而不是「Taiwan Semiconductor Manufacturing」。
    """
    terms = {ticker.lower()}
    if name:
        terms.add(name.lower())
        words = [w for w in re.findall(r"[A-Za-z]{2,}", name) if w.lower() not in _GENERIC]
        terms.update(w.lower() for w in words if len(w) >= 4)
        # 前 N 個字的縮寫：Taiwan Semiconductor Manufacturing → TSM、TSMC…
        for n in range(2, min(len(words), 5) + 1):
            terms.add("".join(w[0] for w in words[:n]).lower())
    return {t for t in terms if len(t) >= 3}


def _is_about(title: str, terms: set[str]) -> bool:
    lowered = title.lower()
    return any(t in lowered for t in terms)


def _fetch_news(ticker: str, name: str = "") -> list[dict]:
    """Return up to 5 fresh (< 48 h) news items as [{title, url}].

    只留標題真的提到這家公司的。yfinance 對 2330.TW 回傳的五則裡有
    三則是 NVIDIA 和 Cisco 的——而 prompt 又要求「不要提及其他公司
    名稱」，模型於是把 NVIDIA 的內容改寫成台積電的樣子送到晨報裡。
    該由程式擋掉的東西，不要留給模型判斷。
    """
    # 台股先試上市（.TW）再試上櫃（.TWO）——跟 stock / charts / metrics /
    # earnings / alert 一致。這裡以前只試 .TW，於是上櫃股票在晨報裡
    # 永遠是「本日無相關新聞」，看起來跟真的沒新聞一模一樣。
    candidates = [f"{ticker}.TW", f"{ticker}.TWO"] if is_taiwan_stock(ticker) else [ticker]
    terms = _match_terms(ticker, name)
    try:
        stock, raw = None, []
        for symbol in candidates:
            stock = yf.Ticker(symbol)
            raw = stock.news or []
            if raw:
                break
        # 台股的名稱是中文（「台積電」），但 yfinance 的標題是英文，
        # 只用中文名比對會把所有新聞濾光。補上英文名才有得比。
        if not re.search(r"[A-Za-z]", name or ""):
            try:
                info = stock.info or {}
                terms |= _match_terms(ticker, info.get("longName") or info.get("shortName") or "")
            except Exception:
                pass
        items = []
        dropped = 0
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
            if not title:
                continue
            if terms and not _is_about(title, terms):
                dropped += 1
                continue
            items.append({"title": html.unescape(title), "url": url})
            if len(items) >= 5:
                break
        if dropped:
            logger.info("news: %s 濾掉 %d 則不是在講這家公司的標題", ticker, dropped)
        return items
    except Exception as e:
        logger.warning("News fetch failed for %s: %s", ticker, e)
        return []


def _build_news_data(tickers: list[str], names: dict[str, str]) -> dict:
    """{ticker: [{title, url}]}。

    以前這裡還順手拼一份給 LLM 的標題區塊，但呼叫端從來沒用過那個回傳值
    ——真正餵給模型的區塊是後面依 active 清單重拼的。
    """
    return {t: _fetch_news(t, names.get(t, "")) for t in tickers}


def _short(ticker: str, prices: dict) -> str:
    """摘要行用的短名稱：只寫公司名，不帶代號（那一行要塞好幾支）。"""
    data = prices.get(ticker) or {}
    name = data.get("name") if isinstance(data, dict) else ""
    return name or ticker


def _highlight(movers: list[str], prices: dict) -> str:
    """最上面那一行：今天到底要看什麼。

    以前整則晨報 67 行、其中 76% 是新聞，今天真正的重點（聯發科漲停）
    要滑過 51 行才拼得出來。這一行是為了讓你三秒內知道今天有沒有事。
    """
    bits = []
    for ticker in movers:
        pct = _day_pct(prices.get(ticker, {}))
        if pct is None:
            continue
        data = prices.get(ticker) or {}
        move = classify_move(ticker, data.get("price") or data.get("close"),
                             data.get("prev_close"))
        tag = f"（{move['headline']}）" if move else ""
        bits.append(f"{_short(ticker, prices)} {pct:+.2f}%{tag}")
    if not bits:
        return ""
    return "⚠️ 今天要看\n" + html.escape("、".join(bits))


async def fetch_and_summarize(tickers: list[str], market_block: str = "") -> str:
    """自選股快報（HTML）。

    版面順序：今天要看 → 大盤（由呼叫端傳入）→ 行情總覽 → 異動股的新聞。

    新聞只給今天有異動（±3%）的股票。以前的規則是「有新聞或有異動」，
    但每支股票每天都有新聞，於是十支列了九支，「無大事」的收合形同失效。
    """
    # 先抓報價：新聞過濾要用公司名稱比對標題，而名稱在報價結果裡。
    # 多一個往返，但晨報一天只跑一次，換來的是不會把別家公司的新聞
    # 摘要成這家的。
    price_results = await asyncio.gather(*[get_stock_summary(t) for t in tickers])
    prices = {t: data for t, data in zip(tickers, price_results)}
    names = {
        t: (prices[t].get("name") or "") if isinstance(prices[t], dict) else ""
        for t in tickers
    }
    # 只有異動股的新聞會被列出來，其餘不必打網路（十支變三支）
    movers_for_news = [
        t for t in tickers
        if abs(_day_pct(prices.get(t, {})) or 0) >= _BIG_MOVE_PCT
    ]
    news_items = await asyncio.to_thread(_build_news_data, movers_for_news, names)

    def _sort_key(t: str):
        pct = _day_pct(prices.get(t, {}))
        return -abs(pct) if pct is not None else 0.0

    # 台股、美股分開排序（各自異動大的排前面），總覽與重點分析都照這個順序
    ordered_tw = sorted((t for t in tickers if is_taiwan_stock(t)), key=_sort_key)
    ordered_us = sorted((t for t in tickers if not is_taiwan_stock(t)), key=_sort_key)
    ordered = ordered_tw + ordered_us

    def _label(t: str) -> str:
        return label(t, prices.get(t, {}))

    # 只有今天真的在動的才單獨列新聞
    movers = [t for t in ordered if abs(_day_pct(prices.get(t, {})) or 0) >= _BIG_MOVE_PCT]
    quiet = [t for t in ordered if t not in movers]

    parts = []

    highlight = _highlight(movers, prices)
    if highlight:
        parts.append(highlight)
    if market_block:
        parts.append(market_block)

    parts.append(_price_overview(ordered_tw, ordered_us, prices))

    if movers:
        parts.append("📰 今日異動股的新聞\n\n" + "\n\n".join(
            _headline_block(t, _label(t), news_items.get(t, []))
            for t in movers
        ))

    if quiet:
        parts.append(html.escape(
            f"😴 其餘 {len(quiet)} 支無異動，新聞可用 /news 查看"
            if movers else
            f"😴 今天 {len(quiet)} 支都沒有明顯異動，新聞可用 /news 查看"
        ))

    return "\n\n".join(parts)
