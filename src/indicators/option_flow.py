"""
Detects option contracts with abnormally high volume / open-interest ratios.

Only contracts expiring at least MIN_DAYS_TO_EXP out are considered — the report is
written for a 6-18 month investment horizon, so weekly/near-dated flow is noise.

OI STALENESS NOTE: yfinance openInterest is settled at prior-day close, not intraday.
Each anomaly dict carries `oi` as its own field so a future caller can substitute a
stored prior-day snapshot without changing the schema.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Dict, List, Optional

from src.data.yf_session import make_ticker

# ── Thresholds (tune here) ────────────────────────────────────────────────────
MIN_OI          = 20    # skip contracts with OI below this — avoids spurious ratios
MIN_VOLUME      = 50    # skip trickle trades
RATIO_THRESHOLD = 1.5   # volume / OI must exceed this to flag as anomalous
MIN_DAYS_TO_EXP = 28    # ignore anything expiring sooner — weeklies say nothing about a 6-18mo thesis
MAX_EXPIRATIONS = 6     # qualifying expiry dates to scan per ticker (first N at/after MIN_DAYS_TO_EXP)
ATM_BAND        = 0.02  # ±2% of spot counts as ATM
MAX_WORKERS     = 6     # concurrent ticker scans
MAX_DISPLAY     = 5     # top contracts shown per ticker in reports
# ─────────────────────────────────────────────────────────────────────────────


def _safe_float(v) -> float:
    """
    Coerce any value to float, returning 0.0 for NaN / None / non-numeric.

    Do NOT use `v or 0` — float('nan') is truthy in Python, so `nan or 0`
    returns nan, not 0. math.isnan() is the only correct guard.
    """
    if v is None:
        return 0.0
    try:
        f = float(v)
        return 0.0 if math.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


def _moneyness(strike: float, spot: float, opt_type: str) -> str:
    ratio = strike / spot
    if abs(ratio - 1.0) <= ATM_BAND:
        return "ATM"
    if opt_type == "call":
        return "ITM" if ratio < 1.0 else "OTM"
    else:
        return "ITM" if ratio > 1.0 else "OTM"


def _term_bucket(days: int) -> str:
    if days <= 30:
        return "near"
    if days <= 270:
        return "mid"
    return "LEAPS"


def _scan_chain(df, opt_type: str, exp_str: str, spot: float, days_to_exp: int, ticker: str) -> List[Dict]:
    bucket    = _term_bucket(days_to_exp)
    anomalies = []
    for row in df.itertuples(index=False):
        strike = _safe_float(getattr(row, "strike",            None))
        volume = int(_safe_float(getattr(row, "volume",        None)))
        oi     = int(_safe_float(getattr(row, "openInterest",  None)))
        iv     = _safe_float(getattr(row, "impliedVolatility", None))
        last   = _safe_float(getattr(row, "lastPrice",         None))

        if oi < MIN_OI or volume < MIN_VOLUME:
            continue
        ratio = volume / oi
        if ratio < RATIO_THRESHOLD:
            continue

        anomalies.append({
            "ticker":      ticker,
            "expiration":  exp_str,
            "strike":      strike,
            "type":        opt_type,
            "moneyness":   _moneyness(strike, spot, opt_type),
            "term":        bucket,
            "days_to_exp": days_to_exp,
            "ratio":       round(ratio, 2),
            "volume":      volume,
            "oi":          oi,       # prior-day settlement value from yfinance
            "iv":          round(iv, 4) if iv else None,
            "last":        round(last, 2) if last else None,
            # Rough traded notional; lastPrice is a stale single print, so treat
            # this as an order-of-magnitude size hint, not an exact dollar figure.
            "premium":     int(volume * last * 100) if last else None,
        })
    return anomalies


def _scan_ticker(ticker: str, prices: Optional[Dict[str, float]]) -> List[Dict]:
    """Scan one ticker across its upcoming expirations. Raises on fatal error."""
    today = date.today()
    t     = make_ticker(ticker)

    exp_dates = list(t.options or [])
    if not exp_dates:
        return []

    spot = (prices or {}).get(ticker)
    if not spot:
        fi   = t.fast_info
        spot = getattr(fi, "last_price", None) or getattr(fi, "regular_market_price", None)
    if not spot or _safe_float(spot) == 0.0:
        print(f"[WARN] [{ticker}] Could not determine spot price — skipping option scan.")
        return []
    spot = float(spot)

    # Long-horizon filter: skip every expiry inside MIN_DAYS_TO_EXP, then take the
    # first MAX_EXPIRATIONS that qualify (yfinance returns expirations ascending).
    dated = []
    for exp_str in exp_dates:
        try:
            days_to_exp = (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if days_to_exp >= MIN_DAYS_TO_EXP:
            dated.append((exp_str, days_to_exp))
    dated = dated[:MAX_EXPIRATIONS]

    anomalies: List[Dict] = []
    for exp_str, days_to_exp in dated:
        try:
            chain = t.option_chain(exp_str)
            for opt_type, df in (("call", chain.calls), ("put", chain.puts)):
                anomalies.extend(_scan_chain(df, opt_type, exp_str, spot, days_to_exp, ticker))
        except Exception as e:
            print(f"[WARN] [{ticker}] Failed to scan expiry {exp_str}: {e}")

    return sorted(anomalies, key=lambda x: x["ratio"], reverse=True)


def scan_all(tickers: List[str], prices: Optional[Dict[str, float]] = None) -> Dict[str, List[Dict]]:
    """
    Scan all tickers for option flow anomalies concurrently.

    Args:
        tickers: watchlist symbols
        prices:  optional pre-fetched {ticker: spot} to avoid redundant API calls

    Returns:
        {ticker: [anomaly, ...]} for tickers that have at least one anomaly,
        each list sorted by ratio descending.
    """
    results: Dict[str, List[Dict]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_ticker = {pool.submit(_scan_ticker, t, prices): t for t in tickers}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                anomalies = future.result()
                if anomalies:
                    results[ticker] = anomalies
            except Exception as e:
                print(f"[WARN] [{ticker}] Option flow scan failed: {e}")
    return results


def _k(n: int) -> str:
    return f"{n/1000:.1f}K" if n >= 1000 else str(n)


def print_report(findings: Dict[str, List[Dict]]) -> None:
    if not findings:
        print("No option flow anomalies detected.")
        return
    for ticker, rows in findings.items():
        display = rows[:MAX_DISPLAY]
        extra   = f"  (+{len(rows) - MAX_DISPLAY} more)" if len(rows) > MAX_DISPLAY else ""
        print(f"\n{ticker}  —  {len(rows)} anomalous contract{'s' if len(rows) != 1 else ''}{extra}")
        for r in display:
            exp_short = datetime.strptime(r["expiration"], "%Y-%m-%d").strftime("%b %d")
            print(
                f"  {exp_short:6}  {r['type'].upper():4} ${r['strike']:>8.1f}  "
                f"{r['moneyness']:3}  {r['ratio']:>5.1f}×  "
                f"{_k(r['volume']):>6} vol / {_k(r['oi']):>6} OI"
            )


if __name__ == "__main__":
    import sys
    watchlist = sys.argv[1:] or ["TSLA", "AMZN", "NVDA"]
    print(f"Scanning option flow for: {watchlist}\n")
    findings = scan_all(watchlist)
    print_report(findings)
