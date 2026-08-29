import os
import re
import asyncio
import httpx
import yfinance as yf
from datetime import date, timedelta

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
_TOKEN = os.getenv("FINMIND_TOKEN", "")


def _token_params() -> dict:
    return {"token": _TOKEN} if _TOKEN else {}


async def _finmind_get(client: httpx.AsyncClient, dataset: str, stock_id: str, start: str) -> list:
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start,
        **_token_params(),
    }
    try:
        resp = await client.get(FINMIND_API, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception:
        return []


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _by_year(rows: list, value_col: str, label_col: str) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        stamp = str(row.get(label_col, ""))
        value = _to_float(row.get(value_col))
        if len(stamp) >= 4 and value is not None:
            grouped.setdefault(stamp[:4], []).append((stamp, value))
    return grouped


def _recent_years(grouped: dict, limit: int = 3) -> list[str]:
    return sorted(sorted(grouped, reverse=True)[:limit])


def _annual_cumulative(rows: list, value_col: str, label_col: str = "date") -> dict:
    """年初至今累計項目（現金流量表）：取每年最後一期，**不能加總**。

    FinMind 同一個 API 有兩種語意，而且沒有任何欄位標明：
      損益表   TaiwanStockFinancialStatements   → 單季數，要加總
      現金流量表 TaiwanStockCashFlowsStatement  → 年初至今累計數

    實測台積電 2024 營業現金流：Q1 4,363 億、H1 8,140、9M 12,060、
    FY 18,262（逐列遞增的累計數）。四列相加得到 4.28 兆，
    真實全年是 1.83 兆——虛報 2.3 倍，而且每份台股分析都吃到這個數字。

    損益表看起來也像逐列遞增，那只是台積電剛好每季成長，不是累計：
    四季相加 2.89 兆，正好等於實際全年營收。
    """
    grouped = _by_year(rows, value_col, label_col)
    result = {}
    for year in _recent_years(grouped):
        stamp, value = max(grouped[year], key=lambda x: x[0])
        label = year if stamp[5:10] == "12-31" else f"{year}（截至 {stamp[5:10]} 累計，非全年）"
        result[label] = value
    return result


def _annual_flow(rows: list, value_col: str, label_col: str = "date") -> dict:
    """流量項目（營收、淨利）：同年度的季報**加總**才是年度數字。

    FinMind 回傳的是單季數字。這裡以前直接取「每年最後一筆」當年度值，
    等於拿某一季冒充整年——實測讓模型拿 2024Q4 比 2026Q2，
    算出「三年成長 12.56 倍」的假成長。年度不齊時在鍵名標明季數。
    """
    grouped = _by_year(rows, value_col, label_col)
    result = {}
    for year in _recent_years(grouped):
        quarters = grouped[year]
        total = sum(v for _, v in quarters)
        # 不寫「前 N 季」——缺的可能是任何一季，只保證「這不是全年」
        label = year if len(quarters) >= 4 else f"{year}（僅 {len(quarters)} 季合計，非全年）"
        result[label] = total
    return result


def _annual_point(rows: list, value_col: str, label_col: str = "date") -> dict:
    """存量項目（總資產、負債、權益）：取每年最新一期即可，不能加總。"""
    grouped = _by_year(rows, value_col, label_col)
    result = {}
    for year in _recent_years(grouped):
        stamp, value = max(grouped[year], key=lambda x: x[0])
        label = year if stamp[5:10] == "12-31" else f"{year}（截至 {stamp[5:10]}）"
        result[label] = value
    return result


def _quarterly_rows(rows: list, date_col: str = "date") -> list:
    """Return the most recent 4 rows sorted by date."""
    sorted_rows = sorted(rows, key=lambda r: r.get(date_col, ""), reverse=True)
    return list(reversed(sorted_rows[:4]))


async def fetch_taiwan_financials(ticker: str) -> dict:
    """Fetch 3-year annual + 4-quarter financial data for a Taiwan stock via FinMind."""
    three_years_ago = (date.today() - timedelta(days=3 * 366)).strftime("%Y-%m-%d")
    one_year_ago = (date.today() - timedelta(days=366)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        income_annual, balance_annual, cashflow_annual, income_quarterly = await asyncio.gather(
            _finmind_get(client, "TaiwanStockFinancialStatements", ticker, three_years_ago),
            _finmind_get(client, "TaiwanStockBalanceSheet", ticker, three_years_ago),
            _finmind_get(client, "TaiwanStockCashFlowsStatement", ticker, three_years_ago),
            _finmind_get(client, "TaiwanStockFinancialStatements", ticker, one_year_ago),
        )

    if not income_annual and not balance_annual:
        return {"error": f"FinMind 無法取得 {ticker} 財報資料"}

    def extract_flow(rows: list, type_val: str, value_col: str = "value") -> dict:
        return _annual_flow([r for r in rows if r.get("type") == type_val], value_col)

    def extract_point(rows: list, type_val: str, value_col: str = "value") -> dict:
        return _annual_point([r for r in rows if r.get("type") == type_val], value_col)

    def extract_metric_quarterly(rows: list, type_val: str, value_col: str = "value") -> list:
        filtered = [r for r in rows if r.get("type") == type_val]
        return _quarterly_rows(filtered)

    # 損益與現金流是流量 → 加總；資產負債是存量 → 取最新一期
    revenue_annual = extract_flow(income_annual, "Revenue")
    # FinMind 沒有 NetIncome 這個型別，用錯名字會靜默回空——台股年度淨利一直是缺的
    net_income_annual = extract_flow(income_annual, "IncomeAfterTaxes")
    gross_profit_annual = extract_flow(income_annual, "GrossProfit")
    operating_income_annual = extract_flow(income_annual, "OperatingIncome")

    total_assets = extract_point(balance_annual, "TotalAssets")
    total_liabilities = extract_point(balance_annual, "TotalLiabilities")
    equity = extract_point(balance_annual, "StockholdersEquity")

    # 費用與稅務科目：少了它們，模型看到「淨利突然掉一個數量級」只能寫「無法判斷」。
    # 實測 META 2025Q3 淨利 27 億的原因就是當季所得稅 190 億，答案只差一行。
    cost_of_goods = extract_flow(income_annual, "CostOfGoodsSold")
    operating_expenses = extract_flow(income_annual, "OperatingExpenses")
    pretax_income = extract_flow(income_annual, "PreTaxIncome")
    tax = extract_flow(income_annual, "TAX")
    eps = extract_flow(income_annual, "EPS")

    # 現金流量表是累計數，取每年最後一期；不可用 extract_flow 加總
    def extract_cumulative(rows: list, type_val: str, value_col: str = "value") -> dict:
        return _annual_cumulative([r for r in rows if r.get("type") == type_val], value_col)

    operating_cf = extract_cumulative(cashflow_annual, "CashFlowsFromOperatingActivities")
    # 型別名稱是 PropertyAndPlantAndEquipment；寫錯名字只會靜默回空陣列，
    # 報告就變成「本次資料未提供資本支出」——跟當初 NetIncome 一模一樣的坑。
    # 值是負數（現金流出），照抄不轉正號。
    capex = extract_cumulative(cashflow_annual, "PropertyAndPlantAndEquipment")

    revenue_q = extract_metric_quarterly(income_quarterly, "Revenue")
    net_income_q = extract_metric_quarterly(income_quarterly, "IncomeAfterTaxes")
    pretax_q = extract_metric_quarterly(income_quarterly, "PreTaxIncome")
    tax_q = extract_metric_quarterly(income_quarterly, "TAX")

    result = {
        "market": "TW",
        "ticker": ticker,
        "annual": {
            "revenue": revenue_annual,
            "net_income": net_income_annual,
            "cost_of_goods": cost_of_goods,
            "gross_profit": gross_profit_annual,
            "operating_expenses": operating_expenses,
            "operating_income": operating_income_annual,
            "pretax_income": pretax_income,
            "tax": tax,
            "eps": eps,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "equity": equity,
            "operating_cashflow": operating_cf,
            "capex": capex,
        },
        "quarterly": {
            "revenue": [{"date": r.get("date"), "value": r.get("value")} for r in revenue_q],
            "net_income": [{"date": r.get("date"), "value": r.get("value")} for r in net_income_q],
            "pretax_income": [{"date": r.get("date"), "value": r.get("value")} for r in pretax_q],
            "tax": [{"date": r.get("date"), "value": r.get("value")} for r in tax_q],
        },
    }

    return result


def fetch_us_financials(ticker: str) -> dict:
    """Fetch 3-year annual + 4-quarter financials for a US stock via yfinance."""
    try:
        stock = yf.Ticker(ticker)

        income = stock.financials  # annual, columns are dates
        quarterly_income = stock.quarterly_financials
        balance = stock.balance_sheet
        cashflow = stock.cashflow

        def safe_series(df, key: str) -> dict:
            if df is None or df.empty or key not in df.index:
                return {}
            row = df.loc[key]
            return {str(col.date()): int(v) for col, v in row.items() if v == v}

        def safe_series_quarterly(df, key: str) -> list:
            if df is None or df.empty or key not in df.index:
                return []
            row = df.loc[key]
            items = [(str(col.date()), int(v)) for col, v in row.items() if v == v]
            items_sorted = sorted(items, key=lambda x: x[0])
            return [{"date": d, "value": v} for d, v in items_sorted[-4:]]

        annual_revenue = safe_series(income, "Total Revenue")
        annual_net_income = safe_series(income, "Net Income")
        annual_gross_profit = safe_series(income, "Gross Profit")
        annual_operating_income = safe_series(income, "Operating Income")
        # 見台股路徑的說明：費用與稅務科目是解釋獲利異常的關鍵
        annual_cost_of_goods = safe_series(income, "Cost Of Revenue")
        annual_operating_expenses = safe_series(income, "Operating Expense")
        annual_rnd = safe_series(income, "Research And Development")
        annual_sga = safe_series(income, "Selling General And Administration")
        annual_pretax = safe_series(income, "Pretax Income")
        annual_tax = safe_series(income, "Tax Provision")
        annual_eps = safe_series(income, "Diluted EPS")
        annual_total_assets = safe_series(balance, "Total Assets")
        annual_total_liabilities = safe_series(balance, "Total Liabilities Net Minority Interest")
        annual_equity = safe_series(balance, "Stockholders Equity")
        annual_operating_cf = safe_series(cashflow, "Operating Cash Flow")
        annual_capex = safe_series(cashflow, "Capital Expenditure")

        quarterly_revenue = safe_series_quarterly(quarterly_income, "Total Revenue")
        quarterly_net_income = safe_series_quarterly(quarterly_income, "Net Income")
        quarterly_pretax = safe_series_quarterly(quarterly_income, "Pretax Income")
        quarterly_tax = safe_series_quarterly(quarterly_income, "Tax Provision")

        return {
            "market": "US",
            "ticker": ticker,
            "annual": {
                "revenue": annual_revenue,
                "net_income": annual_net_income,
                "cost_of_goods": annual_cost_of_goods,
                "gross_profit": annual_gross_profit,
                "rnd": annual_rnd,
                "sga": annual_sga,
                "operating_expenses": annual_operating_expenses,
                "operating_income": annual_operating_income,
                "pretax_income": annual_pretax,
                "tax": annual_tax,
                "eps": annual_eps,
                "total_assets": annual_total_assets,
                "total_liabilities": annual_total_liabilities,
                "equity": annual_equity,
                "operating_cashflow": annual_operating_cf,
                "capex": annual_capex,
            },
            "quarterly": {
                "revenue": quarterly_revenue,
                "net_income": quarterly_net_income,
                "pretax_income": quarterly_pretax,
                "tax": quarterly_tax,
            },
        }
    except Exception as e:
        return {"error": f"yfinance 財報抓取失敗：{e}"}


def _is_taiwan_etf(ticker: str) -> bool:
    """Taiwan ETFs start with '00' (e.g. 0050, 00878, 006208)."""
    return bool(re.match(r'^00\d{2,4}$', ticker))


async def get_financials(ticker: str) -> dict:
    """Main entry: auto-detect TW vs US and fetch financials."""
    from bot.services.stock import is_taiwan_stock
    ticker = ticker.upper().strip()
    if is_taiwan_stock(ticker):
        if _is_taiwan_etf(ticker):
            return {"error": f"{ticker} 為 ETF，無傳統財報；分析將基於淨值、配息與成分股資料"}
        return await fetch_taiwan_financials(ticker)
    return await asyncio.to_thread(fetch_us_financials, ticker)


def format_financials_for_prompt(data: dict) -> str:
    """Convert financials dict to a readable string for the LLM prompt."""
    if "error" in data:
        # 這裡以前寫「以下分析基於模型訓練資料」——等於明文授權模型拿舊記憶當現況。
        # 抓不到就是抓不到，不給任何編造的空間。
        return (
            f"⚠️ 財務數據抓取失敗（{data['error']}）。\n"
            "本次沒有任何財務報表數據可用。嚴禁使用你訓練資料中的財務數字，"
            "所有需要財報數據的章節請整段略過並列入缺漏清單。"
        )

    market = data.get("market", "")
    ticker = data.get("ticker", "")
    annual = data.get("annual", {})
    quarterly = data.get("quarterly", {})

    def fmt_num(v) -> str:
        if v is None:
            return "N/A"
        try:
            n = float(v)
            if abs(n) >= 1e8:
                return f"{n/1e8:.2f}億"
            if abs(n) >= 1e4:
                return f"{n/1e4:.1f}萬"
            return f"{n:.0f}"
        except Exception:
            return str(v)

    def fmt_dict(d: dict) -> str:
        if not d:
            return "N/A"
        return "  ".join(f"{k}: {fmt_num(v)}" for k, v in sorted(d.items()))

    def fmt_list(lst: list) -> str:
        if not lst:
            return "N/A"
        return "  ".join(f"{r.get('date','')}: {fmt_num(r.get('value'))}" for r in lst)

    currency = "TWD" if market == "TW" else "USD"
    lines = [
        f"=== {ticker} 財務數據（{currency}）===",
        "",
        "【年度數據 - 近3年】",
        f"營收：{fmt_dict(annual.get('revenue', {}))}",
        f"毛利：{fmt_dict(annual.get('gross_profit', {}))}",
        f"營業利益：{fmt_dict(annual.get('operating_income', {}))}",
        f"淨利：{fmt_dict(annual.get('net_income', {}))}",
        f"總資產：{fmt_dict(annual.get('total_assets', {}))}",
        f"總負債：{fmt_dict(annual.get('total_liabilities', {}))}",
        f"股東權益：{fmt_dict(annual.get('equity', {}))}",
        f"營業現金流：{fmt_dict(annual.get('operating_cashflow', {}))}",
        f"資本支出（負數＝現金流出）：{fmt_dict(annual.get('capex', {}))}",
        "",
        "【季度數據 - 近4季】",
        f"營收：{fmt_list(quarterly.get('revenue', []))}",
        f"淨利：{fmt_list(quarterly.get('net_income', []))}",
    ]
    return "\n".join(lines)
