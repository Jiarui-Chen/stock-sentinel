from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TimeoutError
from typing import Any, Dict, List

import yfinance as yf

_FETCH_TIMEOUT = 10
_MAX_WORKERS   = 8


def fetch_fundamentals(ticker: str) -> Dict[str, Any]:
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: yf.Ticker(ticker).info)
            try:
                info = future.result(timeout=_FETCH_TIMEOUT)
            except _TimeoutError:
                print(f"[WARN] [{ticker}] Fundamentals fetch timed out — skipping.")
                return {}

        def pct(v):
            return round(v * 100, 1) if v is not None else None

        current = info.get("currentPrice") or info.get("regularMarketPrice")
        target  = info.get("targetMeanPrice")
        high52  = info.get("fiftyTwoWeekHigh")
        low52   = info.get("fiftyTwoWeekLow")

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
        }
    except Exception as e:
        print(f"[WARN] [{ticker}] Fundamentals fetch failed: {e}")
        return {}


def fetch_all(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {t: executor.submit(fetch_fundamentals, t) for t in tickers}
        return {t: f.result() for t, f in futures.items()}
