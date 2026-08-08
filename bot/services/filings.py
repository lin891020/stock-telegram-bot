"""SEC EDGAR：抓美股公司自己寫的財報新聞稿。

這是唯一能拿到「公司對自己的總結與期許」的來源——CEO 原話、官方下季財測，
而且是公司送交主管機關的正式文件，不是第三方轉述，也不需要模型推測。

為什麼不用 yfinance 當觸發器：它是二手資料、有延遲，而且壞掉時無聲
（實測 lxml 缺套件讓財報偵測靜靜死了兩個月）。EDGAR 是第一手，
公司送件當下就有，而且觸發的同時就把報告要用的原文一起拿到了。

SEC 要求每個請求帶可識別的 User-Agent，並限制 10 req/s。
"""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# SEC 硬性要求 User-Agent 長得像「名稱 聯絡信箱」，純網址形式會被擋 403。
# 預設值不寫個人信箱（這是公開 repo），實務上建議用 SEC_USER_AGENT 設成真實聯絡方式。
USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "stock-telegram-bot contact@stock-telegram-bot.local",
)

_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"

_CIK_CACHE = Path("data/sec_cik.json")
_CIK_CACHE_DAYS = 30

# 財報相關表格。外國發行人（如 SKHY）走 6-K/20-F，格式不固定但值得一試。
EARNINGS_FORMS = ("8-K", "6-K")
_EARNINGS_ITEM = "2.02"  # Results of Operations and Financial Condition

# SEC 限 10 req/s；留餘裕
_MIN_INTERVAL = 0.15
_last_request = 0.0


def _sec_get(url: str, timeout: float = 25.0) -> Optional[str]:
    """帶 User-Agent 與節流的 GET。失敗回 None，不拋例外打斷整條流程。"""
    global _last_request
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        logger.warning("SEC request failed (%s): %s", url, e)
        return None


def _load_cik_cache() -> dict:
    if not _CIK_CACHE.exists():
        return {}
    try:
        data = json.loads(_CIK_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    fetched = data.get("fetched", "")
    if not fetched or (date.today() - date.fromisoformat(fetched)).days > _CIK_CACHE_DAYS:
        return {}
    return data.get("map", {})


def _save_cik_cache(mapping: dict) -> None:
    _CIK_CACHE.parent.mkdir(exist_ok=True)
    _CIK_CACHE.write_text(
        json.dumps({"fetched": str(date.today()), "map": mapping}, ensure_ascii=False),
        encoding="utf-8",
    )


def get_cik(ticker: str) -> Optional[int]:
    """美股代號 → SEC CIK。整份對照表快取 30 天（約 1 萬筆）。"""
    ticker = ticker.upper().strip()
    cached = _load_cik_cache()
    if cached:
        value = cached.get(ticker)
        return int(value) if value else None

    raw = _sec_get(_TICKER_MAP_URL)
    if not raw:
        return None
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        return None

    mapping = {
        str(e["ticker"]).upper(): int(e["cik_str"])
        for e in entries.values()
        if e.get("ticker") and e.get("cik_str") is not None
    }
    _save_cik_cache(mapping)
    return mapping.get(ticker)


def list_filings(cik: int, forms: tuple[str, ...], limit: int = 10) -> list[dict]:
    """最近的申報，新到舊。回傳 form / date / accession / primary_doc。"""
    raw = _sec_get(_SUBMISSIONS_URL.format(cik=cik))
    if not raw:
        return []
    try:
        recent = json.loads(raw)["filings"]["recent"]
    except (json.JSONDecodeError, KeyError):
        return []

    results = []
    for form, filed, accession, doc in zip(
        recent.get("form", []), recent.get("filingDate", []),
        recent.get("accessionNumber", []), recent.get("primaryDocument", []),
    ):
        if form not in forms:
            continue
        results.append({
            "form": form,
            "date": filed,
            "accession": accession.replace("-", ""),
            "primary_doc": doc,
        })
        if len(results) >= limit:
            break
    return results


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ENTITIES = {
    "&nbsp;": " ", "&#160;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&#8217;": "'", "&#8216;": "'", "&#8220;": '"', "&#8221;": '"',
    "&#8212;": "—", "&#8211;": "–", "&#58;": ":", "&#8226;": "•", "&#39;": "'",
}


def html_to_text(html: str) -> str:
    """把申報文件的 HTML 轉成乾淨純文字。"""
    text = _SCRIPT_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    for entity, replacement in _ENTITIES.items():
        text = text.replace(entity, replacement)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def filing_items(cik: int, filing: dict) -> set[str]:
    """8-K 的 Item 編號。2.02 = Results of Operations（財報）。"""
    url = _ARCHIVE_BASE.format(cik=cik, accession=filing["accession"]) + "/" + filing["primary_doc"]
    html = _sec_get(url)
    if not html:
        return set()
    return set(re.findall(r"Item\s+(\d\.\d\d)", html_to_text(html)))


_SKIP_DOC = re.compile(r"^(R\d+\.htm|FilingSummary|MetaLinks|.*-index)", re.IGNORECASE)


def filing_exhibits(cik: int, filing: dict) -> list[tuple[str, int]]:
    """申報中的附件 htm 檔，大到小排序。財報新聞稿通常是最大的那個。"""
    url = _ARCHIVE_BASE.format(cik=cik, accession=filing["accession"]) + "/index.json"
    raw = _sec_get(url)
    if not raw:
        return []
    try:
        items = json.loads(raw)["directory"]["item"]
    except (json.JSONDecodeError, KeyError):
        return []

    candidates = []
    for item in items:
        name = item.get("name", "")
        if not name.lower().endswith((".htm", ".html")):
            continue
        if name == filing["primary_doc"] or _SKIP_DOC.match(name):
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        candidates.append((name, size))
    return sorted(candidates, key=lambda x: -x[1])


# 美國公司的財報新聞稿一定講每股盈餘；交車數量、人事異動那種 8-K 不會。
_EPS_MARKERS = ("earnings per share", "per diluted share", "diluted share", "eps")
# 外國發行人（6-K）不一定揭露 EPS。實測 SK hynix 用的是「Revenue / Operating Profit」
# 的韓國格式，有真實季度數字但沒有 EPS，只認 EPS 會整個漏掉。
_STATEMENT_MARKERS = ("operating profit", "operating income")
_MIN_RELEASE_CHARS = 1500


def looks_like_earnings_release(text: str) -> bool:
    if len(text) < _MIN_RELEASE_CHARS:
        return False
    lowered = text.lower()
    if any(m in lowered for m in _EPS_MARKERS):
        return True
    # 營收與獲利同時出現才算；只提到其中一個多半是封面或其他類型公告
    return "revenue" in lowered and any(m in lowered for m in _STATEMENT_MARKERS)


def fetch_earnings_release(ticker: str, max_filings: int = 6) -> Optional[dict]:
    """抓該股最近一次財報新聞稿。

    找不到就回 None——寧可讓報告誠實缺這一段，也不要拿別的文件充數。
    """
    cik = get_cik(ticker)
    if cik is None:
        logger.info("no CIK for %s (非美股或未在 SEC 登記)", ticker)
        return None

    for filing in list_filings(cik, EARNINGS_FORMS, limit=max_filings):
        # 8-K 用 Item 2.02 先篩掉大部分雜訊；6-K 沒有 Item 制度，直接看內容
        if filing["form"] == "8-K" and _EARNINGS_ITEM not in filing_items(cik, filing):
            continue

        base = _ARCHIVE_BASE.format(cik=cik, accession=filing["accession"])
        # 8-K 的主文件通常只是封面，內容在 EX-99 附件；但外國發行人的 6-K
        # 常常沒有附件、內容就寫在主文件裡（實測 SK hynix），所以要留 fallback
        candidates = [name for name, _ in filing_exhibits(cik, filing)[:4]]
        candidates.append(filing["primary_doc"])
        for name in candidates:
            html = _sec_get(f"{base}/{name}")
            if not html:
                continue
            text = html_to_text(html)
            if not looks_like_earnings_release(text):
                continue
            return {
                "ticker": ticker,
                "form": filing["form"],
                "filed": filing["date"],
                "url": f"{base}/{name}",
                "text": text,
                "source": f"SEC EDGAR {filing['form']} {filing['date']}",
            }

    logger.info("no earnings release found for %s", ticker)
    return None
