"""統一的報價格式化，確保各指令（/price /market 卡片 晨報 收盤）顯示一致。

台股報價來源是 TWSE 盤後結算資料（STOCK_DAY），本質是「收盤價」，
所以一律標「收」，避免盤中被誤認為即時價。美股走 yfinance。
"""


def _extract(data: dict):
    """(price, prev_close) — 容錯 price/close 兩種欄位。"""
    price = data.get("price") or data.get("close")
    prev = data.get("prev_close")
    return price, prev


def _unit(data: dict) -> str:
    return "元" if data.get("market") == "TW" else "USD"


def name_label(ticker: str, name: str) -> str:
    """「南亞科(2408)」——名稱拿不到就只回代號，絕不猜。

    報告曾經把 2408 寫成聯電，就是因為名稱沒進到證據包、模型自己填了一個。
    """
    return f"{name}({ticker})" if name and name != ticker else ticker


def label(ticker: str, data: dict) -> str:
    return name_label(ticker, data.get("name", "") if isinstance(data, dict) else "")


def safe_filename(text: str) -> str:
    """檔名用：拿掉路徑分隔字元與控制字元。"""
    cleaned = "".join(c for c in text if c.isprintable() and c not in '/\\:*?"<>|')
    return cleaned.strip().replace(" ", "_")


def change_str(price: float, prev) -> str:
    """漲跌幅字串，無前收盤回空字串。"""
    if not prev:
        return ""
    pct = (price - prev) / prev * 100
    arrow = "▲" if pct >= 0 else "▼"
    sign = "+" if pct >= 0 else ""
    return f"{arrow} {sign}{pct:.2f}%（{sign}{price - prev:.2f}）"


def quote_line(ticker: str, data: dict, multiline: bool = False) -> str:
    """單行（或標籤換行）報價，用於 /price、晨報、收盤速報、卡片。"""
    lbl = label(ticker, data)
    price, prev = _extract(data)
    if not price:
        sep = "\n" if multiline else "："
        return f"{lbl}{sep}無報價"
    sep = "\n" if multiline else "  "
    body = f"收 {price:,.2f} {_unit(data)}"
    chg = change_str(price, prev)
    if chg:
        body += f"  {chg}"
    return f"{lbl}{sep}{body}"
