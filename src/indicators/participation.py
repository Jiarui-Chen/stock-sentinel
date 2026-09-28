"""
Market participation (breadth): what share of the S&P 500 trades above its moving
average, over three horizons.

  short  — % above 20-day SMA
  mid    — % above 50-day SMA
  long   — % above 100-day SMA

Breadth answers a question no single-ticker indicator can: whether a move is
carried by the whole market or by a handful of names. A rally with 30% of the
index above its 20-day average is a narrow rally.

COST
----
One batched yfinance download of ~503 symbols, ~13s. Prices come back in a single
multi-ticker request rather than 503 sequential ones, and the shared session keeps
the fd count flat across runs (verified: repeated downloads plateau and do not
grow). Simple, not exponential, moving averages — the convention for breadth.

We request 6 months (~127 trading days) because the longest window needs 100 prior
closes. Tickers with insufficient history yield NaN and are excluded from that
window's denominator rather than counted as below, so a newly added constituent
cannot drag the reading down.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

import yfinance as yf

from src.data.yf_session import _SESSION

WINDOWS = (20, 50, 100)
_PERIOD = "6mo"

# Standard breadth zones: broad participation, mixed, narrow.
STRONG_THRESHOLD = 70.0
WEAK_THRESHOLD = 30.0


def _download_closes(symbols: List[str]):
    df = yf.download(
        symbols, period=_PERIOD, interval="1d", auto_adjust=True,
        progress=False, threads=True, session=_SESSION,
    )
    if df is None or df.empty:
        raise RuntimeError("yfinance returned no price data for the S&P 500 universe")

    # Single-symbol results come back with flat columns; the real call is always
    # multi-symbol, but keep this honest for tests and one-off debugging.
    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    return closes.dropna(axis=1, how="all")


def compute(symbols: List[str]) -> Dict[str, Any]:
    """
    Percentage of `symbols` closing above their SMA, for each window in WINDOWS.

    Returns {"as_of": date, "requested": int, "universe": int,
             "windows": {20: pct, 50: pct, 100: pct}}
    where each pct carries its own denominator in `counts`, since a short-history
    ticker can be usable for the 20-day window but not the 100-day one.

    Raises RuntimeError if there is too little history to evaluate the longest
    window — better than reporting a number computed from a truncated series.
    """
    closes = _download_closes(symbols)

    if len(closes) < max(WINDOWS):
        raise RuntimeError(
            f"only {len(closes)} trading days returned; need {max(WINDOWS)} "
            f"for the {max(WINDOWS)}-day average"
        )

    windows: Dict[int, float] = {}
    counts: Dict[int, int] = {}
    for window in WINDOWS:
        sma = closes.rolling(window).mean()
        last_close, last_sma = closes.iloc[-1], sma.iloc[-1]
        valid = last_close.notna() & last_sma.notna()
        n = int(valid.sum())
        if n == 0:
            raise RuntimeError(f"no ticker had enough history for the {window}-day average")
        windows[window] = round(float((last_close[valid] > last_sma[valid]).sum()) / n * 100, 1)
        counts[window] = n

    as_of = closes.index[-1]
    return {
        "as_of": as_of.date() if hasattr(as_of, "date") else date.today(),
        "requested": len(symbols),
        "universe": int(closes.shape[1]),
        "windows": windows,
        "counts": counts,
    }


def zone(pct: float) -> str:
    """Breadth zone for `pct`: "strong", "mixed", or "weak"."""
    if pct >= STRONG_THRESHOLD:
        return "strong"
    if pct < WEAK_THRESHOLD:
        return "weak"
    return "mixed"


def fetch_and_compute() -> Dict[str, Any]:
    """Resolve the universe and compute breadth. Raises on unrecoverable failure."""
    from src.data import sp500_fetcher

    symbols, from_cache = sp500_fetcher.fetch_constituents()
    result = compute(symbols)
    result["universe_stale"] = from_cache
    return result


if __name__ == "__main__":  # python3 -m src.indicators.participation
    r = fetch_and_compute()
    print(f"S&P 500 market participation — as of {r['as_of']}"
          f"{'  (cached constituent list)' if r['universe_stale'] else ''}")
    for w in WINDOWS:
        print(f"  above {w:3d}d SMA: {r['windows'][w]:5.1f}%   "
              f"({r['counts'][w]}/{r['requested']} tickers, {zone(r['windows'][w])})")
