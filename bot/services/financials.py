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


def _annual_summary(rows: list, value_col: str, label_col: str = "date") -> dict:
    """Group rows by year and return the latest entry per year (up to 3 years)."""
    by_year: dict[str, dict] = {}
    for row in rows:
        year = str(row.get(label_col, ""))[:4]
        if year:
            by_year[year] = row
    recent_years = sorted(by_year.keys(), reverse=True)[:3]
    return {y: by_year[y].get(value_col) for y in sorted(recent_years)}


def _quarterly_rows(rows: list, date_col: str = "date") -> list:
    """Return the most recent 4 rows sorted by date."""
    sorted_rows = sorted(rows, key=lambda r: r.get(date_col, ""), reverse=True)
    return list(reversed(sorted_rows[:4]))


async def fetch_taiwan_financials(ticker: str) -> dict:
    """Fetch 3-year annual + 4-quarter financial data for a Taiwan stock via FinMind."""
    three_years_ago = (date.today() - timedelta(days=3 * 366)).strftime("%Y-%m-%d")
    one_year_ago = (date.today() - timedelta(days=366)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        income_annual, balance_annual, cashflow_annual, income_quarterly, ratio_data = await asyncio.gather(
            _finmind_get(client, "TaiwanStockFinancialStatements", ticker, three_years_ago),
            _finmind_get(client, "TaiwanStockBalanceSheet", ticker, three_years_ago),
            _finmind_get(client, "TaiwanStockCashFlowsStatement", ticker, three_years_ago),
            _finmind_get(client, "TaiwanStockFinancialStatements", ticker, one_year_ago),
            _finmind_get(client, "TaiwanStockStockNote", ticker, three_years_ago),
        )

    if not income_annual and not balance_annual:
        return {"error": f"FinMind 無法取得 {ticker} 財報資料"}

    def extract_metric(rows: list, type_val: str, value_col: str = "value") -> dict:
        filtered = [r for r in rows if r.get("type") == type_val]
        return _annual_summary(filtered, value_col)

    def extract_metric_quarterly(rows: list, type_val: str, value_col: str = "value") -> list:
        filtered = [r for r in rows if r.get("type") == type_val]
        return _quarterly_rows(filtered)

    revenue_annual = extract_metric(income_annual, "Revenue")
    net_income_annual = extract_metric(income_annual, "NetIncome")
    gross_profit_annual = extract_metric(income_annual, "GrossProfit")
    operating_income_annual = extract_metric(income_annual, "OperatingIncome")

    total_assets = extract_metric(balance_annual, "TotalAssets")
    total_liabilities = extract_metric(balance_annual, "TotalLiabilities")
    equity = extract_metric(balance_annual, "StockholdersEquity")

    operating_cf = extract_metric(cashflow_annual, "CashFlowsFromOperatingActivities")
    capex = extract_metric(cashflow_annual, "AcquisitionOfPropertyPlantAndEquipment")

    revenue_q = extract_metric_quarterly(income_quarterly, "Revenue")
    net_income_q = extract_metric_quarterly(income_quarterly, "NetIncome")

    result = {
        "market": "TW",
        "ticker": ticker,
        "annual": {
            "revenue": revenue_annual,
            "net_income": net_income_annual,
            "gross_profit": gross_profit_annual,
            "operating_income": operating_income_annual,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "equity": equity,
            "operating_cashflow": operating_cf,
            "capex": capex,
        },
        "quarterly": {
            "revenue": [{"date": r.get("date"), "value": r.get("value")} for r in revenue_q],
            "net_income": [{"date": r.get("date"), "value": r.get("value")} for r in net_income_q],
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
        annual_total_assets = safe_series(balance, "Total Assets")
        annual_total_liabilities = safe_series(balance, "Total Liabilities Net Minority Interest")
        annual_equity = safe_series(balance, "Stockholders Equity")
        annual_operating_cf = safe_series(cashflow, "Operating Cash Flow")
        annual_capex = safe_series(cashflow, "Capital Expenditure")

        quarterly_revenue = safe_series_quarterly(quarterly_income, "Total Revenue")
        quarterly_net_income = safe_series_quarterly(quarterly_income, "Net Income")

        return {
            "market": "US",
            "ticker": ticker,
            "annual": {
                "revenue": annual_revenue,
                "net_income": annual_net_income,
                "gross_profit": annual_gross_profit,
                "operating_income": annual_operating_income,
                "total_assets": annual_total_assets,
                "total_liabilities": annual_total_liabilities,
                "equity": annual_equity,
                "operating_cashflow": annual_operating_cf,
                "capex": annual_capex,
            },
            "quarterly": {
                "revenue": quarterly_revenue,
                "net_income": quarterly_net_income,
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
        return f"⚠️ 財務數據抓取失敗（{data['error']}），以下分析基於模型訓練資料，請自行驗證數字。"

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
        f"資本支出：{fmt_dict(annual.get('capex', {}))}",
        "",
        "【季度數據 - 近4季】",
        f"營收：{fmt_list(quarterly.get('revenue', []))}",
        f"淨利：{fmt_list(quarterly.get('net_income', []))}",
    ]
    return "\n".join(lines)
