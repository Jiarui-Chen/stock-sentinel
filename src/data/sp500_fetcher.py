"""
S&P 500 constituent list, from Wikipedia with a local cache fallback.

WHY WIKIPEDIA
-------------
There is no free constituent feed in this project's stack. FMP_API_KEY exists in
config but is unset in every environment and unused everywhere, and yfinance
exposes no index membership. Wikipedia's list table is maintained, free, and
costs ~0.3s to fetch.

Two wrinkles worth knowing:

  * ``pandas.read_html(url)`` gets HTTP 403 — Wikipedia rejects its default
    user-agent. We fetch through the shared yfinance session, whose browser
    user-agent is accepted, and parse the HTML we already hold.

  * The list holds ~503 symbols, not 500: a few companies have two share classes
    (BRK.B, BF.B). Those use dots, which Yahoo spells with hyphens (BRK-B).

WHY THE CACHE
-------------
It is a scrape, so it can break on a layout change or an outage. Every successful
fetch is written to logs/, and a failure falls back to the last good list — index
membership changes a few times a year, so a list that is days or weeks stale still
produces a sound breadth reading. The fallback is reported to the caller so the
staleness can be surfaced rather than hidden.
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from src.data.yf_session import _SESSION

_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_CACHE_FILE = Path(__file__).resolve().parents[2] / "logs" / "sp500_constituents.json"

# The table has changed shape before; anything far off this is a parse failure,
# not an index event, and should fall back to the cache rather than be trusted.
_MIN_PLAUSIBLE = 450
_MAX_PLAUSIBLE = 550


def _to_yahoo(symbol: str) -> str:
    """BRK.B -> BRK-B. Yahoo spells share classes with a hyphen."""
    return symbol.strip().upper().replace(".", "-")


def _scrape() -> List[str]:
    resp = _SESSION.get(_WIKI_URL, timeout=20)
    resp.raise_for_status()

    table = pd.read_html(io.StringIO(resp.text))[0]
    if "Symbol" not in table.columns:
        raise ValueError(f"no 'Symbol' column in Wikipedia table; got {list(table.columns)}")

    symbols = [_to_yahoo(s) for s in table["Symbol"].astype(str) if s and s != "nan"]
    if not _MIN_PLAUSIBLE <= len(symbols) <= _MAX_PLAUSIBLE:
        raise ValueError(f"implausible constituent count {len(symbols)} — treating as a parse failure")
    return symbols


def _read_cache() -> Tuple[List[str], str] | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_CACHE_FILE.read_text())
        symbols = data.get("symbols") or []
        return (symbols, data.get("fetched", "unknown")) if symbols else None
    except (OSError, ValueError) as e:
        print(f"[WARN] S&P 500 cache unreadable: {e}")
        return None


def _write_cache(symbols: List[str]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(
            {"fetched": date.today().isoformat(), "symbols": symbols}, indent=2,
        ))
    except OSError as e:
        print(f"[WARN] Could not cache S&P 500 list: {e}")


def fetch_constituents() -> Tuple[List[str], bool]:
    """
    Return (symbols, from_cache) in Yahoo notation.

    Raises RuntimeError only when the scrape fails AND no cache exists — there is
    no sensible breadth reading without a universe.
    """
    try:
        symbols = _scrape()
        _write_cache(symbols)
        return symbols, False
    except Exception as e:
        print(f"[WARN] S&P 500 constituent fetch failed: {e}")
        cached = _read_cache()
        if cached is None:
            raise RuntimeError(f"no S&P 500 constituent list available: {e}") from e
        symbols, fetched = cached
        print(f"  Falling back to cached list of {len(symbols)} symbols (fetched {fetched}).")
        return symbols, True
