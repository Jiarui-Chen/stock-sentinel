"""
Fetches historical earnings dates and computes how the stock moved in the
10 trading days before and after each of the last N earnings calls.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

_MAX_QUARTERS = 8
_WINDOW       = 10   # trading days before / after earnings
_STATE_FILE   = Path(__file__).resolve().parents[2] / "logs" / "pre_earnings_sent.json"


# ── Send-state ────────────────────────────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    _STATE_FILE.parent.mkdir(exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def _entry_date(entry) -> Optional[str]:
    """Extract earnings date from either legacy str entry or new dict entry."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("earnings_date")
    return None


def already_sent(ticker: str, upcoming_earnings_date: str) -> bool:
    """True if we already sent the pre-earnings email for this specific earnings date."""
    return _entry_date(_load_state().get(ticker)) == upcoming_earnings_date


def mark_sent(
    ticker: str,
    upcoming_earnings_date: str,
    watch_points: Optional[List[Any]] = None,
) -> None:
    state = _load_state()
    state[ticker] = {"earnings_date": upcoming_earnings_date, "watch_points": watch_points}
    _save_state(state)


def get_watch_points(ticker: str, earnings_date: Optional[str]) -> Optional[List[str]]:
    """Return the stored watch points for a ticker's earnings event, or None."""
    entry = _load_state().get(ticker)
    if entry is None or _entry_date(entry) != earnings_date:
        return None
    if isinstance(entry, dict):
        return entry.get("watch_points") or None
    return None


# ── Price history helpers ─────────────────────────────────────────────────────

def _find_pos(trading_dates: pd.DatetimeIndex, target: date) -> Optional[int]:
    """
    Return the index position of the first trading day on or after target.
    Returns None if target is beyond available data.
    """
    # trading_dates is tz-aware; localize the target date to match
    ts = pd.Timestamp(target).tz_localize(trading_dates.tz)
    ahead = trading_dates[trading_dates >= ts]
    if ahead.empty:
        return None
    loc = trading_dates.get_loc(ahead[0])
    return int(loc) if isinstance(loc, (int, type(None))) else int(loc.start)


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_history(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """
    Returns a list of dicts, one per historical earnings quarter (most recent first):
        {
          "earnings_date": "2025-06-10",
          "pre_return":     -0.032,   # (close on earnings day / close 10 td before) - 1
          "post_return":     0.051,   # (close 10 td after / close on earnings day) - 1
                                      # None if insufficient subsequent data
        }
    Returns None if there is not enough history to produce at least one data point.
    """
    try:
        t     = yf.Ticker(ticker)
        ed_df = t.earnings_dates
        if ed_df is None or ed_df.empty:
            return None

        # earnings_dates index is tz-aware (America/New_York); match it explicitly
        today     = pd.Timestamp.now(tz="America/New_York").normalize()
        past      = ed_df[ed_df.index < today].sort_index(ascending=False)
        if past.empty:
            return None

        past_dates = list(past.index[: _MAX_QUARTERS])

        hist = t.history(period="3y")
        if hist is None or hist.empty:
            return None

        closes        = hist["Close"]
        trading_dates = closes.index.normalize()

        results = []
        for ts in past_dates:
            ed  = ts.date()
            pos = _find_pos(trading_dates, ed)
            if pos is None:
                continue

            pre_pos = pos - _WINDOW
            if pre_pos < 0:
                continue  # not enough history before this earnings

            price_pre      = closes.iloc[pre_pos]
            price_earnings = closes.iloc[pos]
            if price_pre <= 0 or price_earnings <= 0:
                continue

            pre_return = (price_earnings - price_pre) / price_pre

            # Post-return is optional: skip if we don't have enough data after
            post_pos  = pos + _WINDOW
            post_return = None
            if post_pos < len(closes):
                price_post = closes.iloc[post_pos]
                if price_post > 0:
                    post_return = (price_post - price_earnings) / price_earnings

            results.append({
                "earnings_date": ed.isoformat(),
                "pre_return":    round(pre_return, 4),
                "post_return":   round(post_return, 4) if post_return is not None else None,
            })

        return results if results else None

    except Exception as e:
        print(f"[WARN] [{ticker}] Pre-earnings history fetch failed: {e}")
        return None
