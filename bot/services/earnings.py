import asyncio
import logging

import yfinance as yf
import pandas as pd

from bot.services.stock import is_taiwan_stock

logger = logging.getLogger(__name__)


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _fetch_earnings_sync(ticker: str) -> dict:
    yf_ticker = f"{ticker}.TW" if is_taiwan_stock(ticker) else ticker
    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info or {}
    except Exception as e:
        return {"ticker": ticker, "error": f"查無股票代號 {ticker}（{e}）"}

    name = info.get("longName") or info.get("shortName") or ticker

    if not info.get("longName") and not info.get("currentPrice"):
        return {"ticker": ticker, "error": f"查無股票代號 {ticker}，請確認是否正確（例如 Micron → MU）"}

    # Next earnings date
    next_date = None
    try:
        cal = stock.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed:
                next_date = str(ed[0])[:10] if hasattr(ed, "__len__") else str(ed)[:10]
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"].iloc[0]
                next_date = str(val)[:10]
    except Exception:
        pass

    # EPS history from earnings_dates (last 4 reported quarters)
    quarters = []
    try:
        df = stock.earnings_dates
        if df is not None and not df.empty:
            # Filter by non-null Reported EPS instead of date comparison
            # (earnings_dates index is tz-aware; date.today() is tz-naive)
            if "Reported EPS" in df.columns:
                reported = df[df["Reported EPS"].notna()].head(4)
            else:
                reported = df.head(4)
            for dt, row in reported.iterrows():
                eps_est = _safe_float(row.get("EPS Estimate"))
                eps_act = _safe_float(row.get("Reported EPS"))
                surprise = _safe_float(row.get("Surprise(%)"))
                quarters.append({
                    "date": str(dt)[:10],
                    "eps_estimate": eps_est,
                    "eps_actual": eps_act,
                    "eps_surprise_pct": surprise,
                    "revenue": None,
                })
    except Exception as e:
        logger.warning("earnings_dates failed for %s: %s", ticker, e)

    # Revenue from quarterly income statement
    try:
        qis = stock.quarterly_income_stmt
        if qis is not None and not qis.empty:
            rev_row = None
            for label in ("Total Revenue", "Revenue"):
                if label in qis.index:
                    rev_row = qis.loc[label]
                    break
            if rev_row is not None:
                for i, (col, val) in enumerate(rev_row.items()):
                    col_date = str(col)[:10]
                    rev = _safe_float(val)
                    if rev is not None:
                        rev = rev / 1e9  # convert to billions
                    if i < len(quarters):
                        quarters[i]["revenue"] = rev
                    else:
                        quarters.append({
                            "date": col_date,
                            "eps_estimate": None,
                            "eps_actual": None,
                            "eps_surprise_pct": None,
                            "revenue": rev,
                        })
                    if i >= 3:
                        break
    except Exception as e:
        logger.warning("quarterly_income_stmt failed for %s: %s", ticker, e)

    return {
        "ticker": ticker,
        "name": name,
        "next_earnings_date": next_date,
        "quarters": quarters,
        "error": None,
    }


async def fetch_earnings_data(ticker: str) -> dict:
    return await asyncio.to_thread(_fetch_earnings_sync, ticker)
