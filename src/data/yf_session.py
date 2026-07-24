"""
Shared HTTP session for all yfinance access.

WHY THIS EXISTS
---------------
yfinance mints a brand-new curl_cffi Session for *every* ``yf.Ticker()`` object
(``yfinance.base.TickerBase.__init__``) and again for *every* ``.history()``
call (``yfinance.scrapers.history.PriceHistory.__init__`` — both do
``session or new_session()``). ``curl_cffi.Session`` has **no ``__del__``**, so
nothing closes the underlying libcurl handle unless ``close()`` is called
explicitly. Under launchd the process runs for days and re-fetches the whole
watchlist several times a day, so these throwaway sessions — plus the sockets
and pipes their libcurl handles hold — pile up until we blow past macOS's
256-fd soft limit and every ``open()`` starts failing with EMFILE (Errno 24).

THE FIX
-------
Reuse ONE module-level session everywhere: pass it into
``yf.Ticker(..., session=...)`` so the ``YfData`` singleton and every Ticker
share it instead of creating new ones per call. For the one place we cannot
inject a session — the ``PriceHistory`` object yfinance lazily builds inside
``.history()`` — ``ticker_scope()`` closes that leftover session as soon as the
Ticker goes out of scope.

A single shared curl_cffi Session is safe across the ThreadPoolExecutors in the
fetchers: curl_cffi keeps a *thread-local* curl handle per Session, and
yfinance's ``YfData`` singleton already shares one session across every thread
today. The session is closed at interpreter exit via ``atexit``.
"""
from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Iterator

import yfinance as yf
from yfinance._http import new_session

# One session for the whole process. new_session() selects the correct backend
# (curl_cffi with chrome impersonation, or plain requests as a fallback) and
# applies yfinance's own headers.
_SESSION = new_session()


@atexit.register
def _close_session() -> None:
    try:
        _SESSION.close()
    except Exception:
        pass


def make_ticker(symbol: str) -> yf.Ticker:
    """A Ticker bound to the shared session (no per-call session creation)."""
    return yf.Ticker(symbol, session=_SESSION)


def _close_leftovers(t: yf.Ticker) -> None:
    """
    Close any throwaway session yfinance created behind our back — currently the
    one inside the lazily-built PriceHistory. Never touch the shared session.
    """
    ph = getattr(t, "_price_history", None)
    if ph is None:
        return
    s = getattr(ph, "session", None)
    if s is not None and s is not _SESSION:
        try:
            s.close()
        except Exception:
            pass


@contextmanager
def ticker_scope(symbol: str) -> Iterator[yf.Ticker]:
    """
    Yield a Ticker on the shared session and guarantee its leftover per-object
    sessions (e.g. the one PriceHistory builds for ``.history()``) are closed
    when the block exits.
    """
    t = make_ticker(symbol)
    try:
        yield t
    finally:
        _close_leftovers(t)
