from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TimeoutError
from typing import Any, Dict, List

from src.data.yf_session import make_ticker

_FETCH_TIMEOUT = 10
_MAX_WORKERS   = 8


def _fetch_ticker_data(ticker: str):
    t = make_ticker(ticker)
    ed_df = None
    try:
        ed_df = t.earnings_dates
    except Exception:
        pass
    return t.info, (t.calendar or {}), ed_df


def fetch_fundamentals(ticker: str) -> Dict[str, Any]:
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch_ticker_data, ticker)
            try:
                info, cal, ed_df = future.result(timeout=_FETCH_TIMEOUT)
            except _TimeoutError:
                print(f"[WARN] [{ticker}] Fundamentals fetch timed out — skipping.")
                return {}

        def pct(v):
            return round(v * 100, 1) if v is not None else None

        current = info.get("currentPrice") or info.get("regularMarketPrice")
        target  = info.get("targetMeanPrice")
        high52  = info.get("fiftyTwoWeekHigh")
        low52   = info.get("fiftyTwoWeekLow")

        # Upcoming earnings date + timing (BMO/AMC)
        earnings_date   = None
        earnings_timing = None  # "BMO" | "AMC" | None
        try:
            dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
            if dates:
                ed = dates[0]
                # Primary: check hour from calendar timestamp (works when yfinance includes time)
                if hasattr(ed, "hour") and ed.hour != 0:
                    earnings_timing = "BMO" if ed.hour < 12 else "AMC"
                if hasattr(ed, "date"):
                    ed = ed.date()
                earnings_date = ed.isoformat()
                # Fallback: earnings_dates DataFrame has explicit "Earnings Call Time" column
                if earnings_timing is None and ed_df is not None and not ed_df.empty:
                    for idx in ed_df.index:
                        idx_date = idx.date() if hasattr(idx, "date") else idx
                        if idx_date == ed:
                            val = ed_df.loc[idx].get("Earnings Call Time", "")
                            if val in ("BMO", "AMC"):
                                earnings_timing = val
                            break
        except Exception:
            pass

        return {
            "pe_trailing":      round(info["trailingPE"], 1) if info.get("trailingPE") else None,
            "pe_forward":       round(info["forwardPE"],  1) if info.get("forwardPE")  else None,
            "revenue_growth":   pct(info.get("revenueGrowth")),
            "earnings_growth":  pct(info.get("earningsGrowth")),
            "profit_margin":    pct(info.get("profitMargins")),
            "analyst_target":   round(target, 2)  if target  else None,
            "current_price":    round(current, 2) if current else None,
            "upside_to_target": round((target / current - 1) * 100, 1) if target and current else None,
            "pct_from_52w_high": round((current / high52 - 1) * 100, 1) if current and high52 else None,
            "pct_from_52w_low":  round((current / low52  - 1) * 100, 1) if current and low52  else None,
            "earnings_date":    earnings_date,
            "earnings_timing":  earnings_timing,
        }
    except Exception as e:
        print(f"[WARN] [{ticker}] Fundamentals fetch failed: {e}")
        return {}


def fetch_all(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {t: executor.submit(fetch_fundamentals, t) for t in tickers}
        return {t: f.result() for t, f in futures.items()}
