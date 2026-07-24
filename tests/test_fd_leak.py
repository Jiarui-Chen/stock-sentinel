"""
Regression guard for the file-descriptor leak that crash-looped Stock Sentinel.

The leak came from yfinance minting (and never closing) a new curl_cffi Session
per Ticker/.history() call. The fixes live in src/data/yf_session.py (a single
reused session + explicit close of leftovers) and the fetcher modules.

Two layers of protection:

  * Hermetic unit checks — always run, no network needed. They pin the two
    invariants the fix relies on: one shared session is reused across Tickers,
    and ticker_scope closes throwaway per-object sessions without ever closing
    the shared one.

  * An integration check — gated on network availability, skipped offline. It
    loops the real fetchers N times and asserts the process's open-fd count
    stays roughly flat, catching any future leak the unit checks can't model.

Runs under pytest, or standalone: `python3 tests/test_fd_leak.py`.
"""
from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data import yf_session

try:
    import pytest
except ImportError:  # standalone run without pytest installed
    pytest = None


def _fd_count() -> int:
    return len(os.listdir("/dev/fd"))


def _network_up(host: str = "finance.yahoo.com", port: int = 443, timeout: int = 5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _skip(reason: str) -> None:
    if pytest is not None:
        pytest.skip(reason)
    print(f"SKIP: {reason}")


# ── Hermetic unit checks ──────────────────────────────────────────────────────

def test_shared_session_is_reused():
    """Every Ticker must ride the one shared session — no per-call creation."""
    a = yf_session.make_ticker("AAPL")
    b = yf_session.make_ticker("MSFT")
    assert a.session is yf_session._SESSION
    assert b.session is yf_session._SESSION


def test_close_leftovers_closes_price_history_session():
    """ticker_scope must close the throwaway session yfinance builds for .history()."""
    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    leftover = FakeSession()

    t = yf_session.make_ticker("AAPL")
    # Simulate the PriceHistory object yfinance lazily attaches on .history().
    t._price_history = type("FakePH", (), {"session": leftover})()

    yf_session._close_leftovers(t)

    assert leftover.closed is True, "leftover PriceHistory session was not closed"
    # The shared session must survive leftover cleanup untouched.
    assert t.session is yf_session._SESSION


def test_close_leftovers_never_closes_shared_session():
    """If a leftover *is* the shared session, it must not be closed."""
    t = yf_session.make_ticker("AAPL")
    t._price_history = type("FakePH", (), {"session": yf_session._SESSION})()
    yf_session._close_leftovers(t)
    # Shared session still usable (curl_cffi/requests sessions expose `.close`,
    # and a closed one would have _closed=True on curl_cffi).
    assert getattr(yf_session._SESSION, "_closed", False) is False


# ── Integration check (network-gated) ─────────────────────────────────────────

def test_fd_count_stable_across_fetches():
    """Open-fd count must not grow monotonically across repeated real fetches."""
    if not _network_up():
        _skip("network unavailable — skipping fd-leak integration check")
        return

    from src.data import fetcher, news_fetcher, fundamentals_fetcher
    from src.indicators import option_flow

    syms = ["AAPL", "MSFT"]

    # Warm-up: the first calls open one-time fds (shared session connections, DNS
    # caches) that are then reused. Measure the baseline AFTER warm-up so we test
    # steady-state growth, not first-touch setup.
    fetcher.fetch_daily("AAPL")
    news_fetcher.fetch_all(syms)
    fundamentals_fetcher.fetch_all(syms)
    option_flow.scan_all(syms)

    baseline = _fd_count()
    counts = []
    for _ in range(4):
        fetcher.fetch_daily("AAPL")
        fetcher.fetch_weekly("MSFT")
        news_fetcher.fetch_all(syms)
        fundamentals_fetcher.fetch_all(syms)
        option_flow.scan_all(syms)
        counts.append(_fd_count())

    growth = counts[-1] - baseline
    # A tiny wobble (kept-alive sockets recycling) is fine; a real leak grows by
    # dozens per iteration. Fail if we drift more than a small constant.
    assert growth <= 5, (
        f"open fds grew by {growth} across 4 fetch loops "
        f"(baseline={baseline}, per-iter={counts}) — likely an fd leak"
    )


if __name__ == "__main__":
    failures = 0
    tests = [
        test_shared_session_is_reused,
        test_close_leftovers_closes_price_history_session,
        test_close_leftovers_never_closes_shared_session,
        test_fd_count_stable_across_fetches,
    ]
    for fn in tests:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {fn.__name__}\n    {e}")
    sys.exit(1 if failures else 0)
