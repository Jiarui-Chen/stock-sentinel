"""
Checks for the market-participation (breadth) metric.

Breadth is the share of S&P 500 constituents closing above their 20/50/100-day
simple moving average. It leads every daily report, so a wrong number here is the
first thing the reader sees and the frame they judge everything else against.

What is pinned:

  * the arithmetic, against a synthetic universe with a known answer,
  * that short-history tickers leave a window's denominator rather than counting
    as "below" — otherwise every index addition would drag breadth down,
  * that too little history is an error, not a number computed from a stub,
  * zone thresholds and their colors,
  * that the block leads the email, renders in both languages, and disappears
    cleanly when the metric is unavailable.

All hermetic — the price download and the Wikipedia scrape are both stubbed, so
these run offline. Standalone: `python3 tests/test_participation.py`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import degradation, i18n
from src.data import sp500_fetcher
from src.indicators import participation
from src.report import email_reporter

_DAYS = 130


def _frame(series: dict) -> pd.DataFrame:
    """A daily close frame indexed by business days, one column per ticker."""
    idx = pd.date_range("2026-01-01", periods=_DAYS, freq="B")
    return pd.DataFrame(series, index=idx)


def _rising(n=_DAYS):
    return np.linspace(100, 200, n)


def _falling(n=_DAYS):
    return np.linspace(200, 100, n)


def _with_stub(frame, fn):
    """Run fn() with the price download stubbed out to return `frame`."""
    original = participation._download_closes
    participation._download_closes = lambda symbols: frame
    try:
        return fn()
    finally:
        participation._download_closes = original


# ── arithmetic ────────────────────────────────────────────────────────────────

def test_percentages_match_known_universe():
    """Two of three names rising ⇒ 66.7% above, on every window."""
    frame = _frame({"UP1": _rising(), "UP2": _rising(), "DOWN": _falling()})
    r = _with_stub(frame, lambda: participation.compute(["UP1", "UP2", "DOWN"]))
    for window in participation.WINDOWS:
        assert r["windows"][window] == 66.7, f"{window}d: {r['windows'][window]}"
        assert r["counts"][window] == 3
    assert r["universe"] == 3
    assert r["as_of"] == frame.index[-1].date()


def test_all_above_and_all_below_are_100_and_0():
    up = _with_stub(_frame({"A": _rising(), "B": _rising()}),
                    lambda: participation.compute(["A", "B"]))
    down = _with_stub(_frame({"A": _falling(), "B": _falling()}),
                      lambda: participation.compute(["A", "B"]))
    assert all(up["windows"][w] == 100.0 for w in participation.WINDOWS), up["windows"]
    assert all(down["windows"][w] == 0.0 for w in participation.WINDOWS), down["windows"]


def test_short_history_leaves_denominator_not_counted_as_below():
    """
    A ticker with 60 days has no 100-day average. It must drop out of that
    window's denominator — counting it as "below" would understate breadth every
    time the index adds a name.
    """
    short = np.concatenate([np.full(_DAYS - 60, np.nan), _rising(60)])
    frame = _frame({"FULL": _rising(), "NEW": short})
    r = _with_stub(frame, lambda: participation.compute(["FULL", "NEW"]))
    assert r["counts"][20] == 2, r["counts"]
    assert r["counts"][100] == 1, "short-history ticker still in the 100d denominator"
    assert r["windows"][100] == 100.0, r["windows"]


def test_insufficient_history_raises():
    """Never report a 100-day figure computed from fewer than 100 closes."""
    idx = pd.date_range("2026-01-01", periods=50, freq="B")
    frame = pd.DataFrame({"A": _rising(50)}, index=idx)
    try:
        _with_stub(frame, lambda: participation.compute(["A"]))
    except RuntimeError as e:
        assert "trading days" in str(e), e
        return
    raise AssertionError("expected RuntimeError for insufficient history")


# ── zones ─────────────────────────────────────────────────────────────────────

def test_zone_thresholds():
    assert participation.zone(70.0) == "strong"
    assert participation.zone(99.9) == "strong"
    assert participation.zone(69.9) == "mixed"
    assert participation.zone(30.0) == "mixed"
    assert participation.zone(29.9) == "weak"
    assert participation.zone(0.0) == "weak"


# ── universe resolution ───────────────────────────────────────────────────────

def test_share_class_symbols_converted_for_yahoo():
    assert sp500_fetcher._to_yahoo("BRK.B") == "BRK-B"
    assert sp500_fetcher._to_yahoo(" aapl ") == "AAPL"


def test_cache_fallback_when_scrape_fails():
    """A Wikipedia outage must not cost the section — reuse the last good list."""
    original_scrape, original_cache = sp500_fetcher._scrape, sp500_fetcher._CACHE_FILE
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "sp500.json"
        cache.write_text(json.dumps({"fetched": "2026-09-01", "symbols": ["AAPL", "MSFT"]}))
        sp500_fetcher._CACHE_FILE = cache
        sp500_fetcher._scrape = lambda: (_ for _ in ()).throw(RuntimeError("simulated 403"))
        try:
            symbols, from_cache = sp500_fetcher.fetch_constituents()
            assert symbols == ["AAPL", "MSFT"], symbols
            assert from_cache is True
        finally:
            sp500_fetcher._scrape, sp500_fetcher._CACHE_FILE = original_scrape, original_cache


def test_no_cache_and_failed_scrape_raises():
    """With no universe at all there is no honest number to report."""
    original_scrape, original_cache = sp500_fetcher._scrape, sp500_fetcher._CACHE_FILE
    with tempfile.TemporaryDirectory() as d:
        sp500_fetcher._CACHE_FILE = Path(d) / "absent.json"
        sp500_fetcher._scrape = lambda: (_ for _ in ()).throw(RuntimeError("simulated 403"))
        try:
            sp500_fetcher.fetch_constituents()
        except RuntimeError:
            return
        finally:
            sp500_fetcher._scrape, sp500_fetcher._CACHE_FILE = original_scrape, original_cache
    raise AssertionError("expected RuntimeError with no cache and a failed scrape")


# ── rendering ─────────────────────────────────────────────────────────────────

# One value per zone: 28.2 weak (< 30), 72.4 strong (>= 70), 55.0 mixed.
_PART = {
    "as_of": "2026-09-25", "requested": 503, "universe": 503,
    "windows": {20: 28.2, 50: 72.4, 100: 55.0},
    "counts": {20: 503, 50: 503, 100: 501},
    "universe_stale": False,
}


def _html(part=_PART, degradations=()):
    return email_reporter.build_html([], None, None, None, list(degradations), part)


def test_block_leads_the_email():
    """The metric is meant to frame everything below it, so it must come first."""
    html = _html()
    others = [i18n.t(k) for k in ("sec_picks", "sec_scorecard", "sec_news", "sec_flow")]
    pos = html.index(i18n.t("sec_participation"))
    for label in others:
        if label in html:
            assert pos < html.index(label), f"participation not before {label}"


def test_all_three_horizons_and_zones_render():
    html = _html()
    text = re.sub(r"<[^>]+>", " ", html)
    for pct in ("28.2%", "72.4%", "55.0%"):
        assert pct in text, f"missing {pct}"
    # 28.2 weak, 72.4 strong, 55.0 mixed — each zone label must appear
    for key in ("zone_weak", "zone_strong", "zone_mixed"):
        assert i18n.t(key) in text, f"missing {key}"
    # and the colors that go with them
    for color in ("#dc2626", "#16a34a", "#d97706"):
        assert color in html, f"missing {color}"


def test_absent_metric_renders_no_block():
    assert i18n.t("sec_participation") not in _html(part=None)


def test_stale_universe_is_disclosed():
    assert i18n.t("part_stale") not in _html()
    stale = {**_PART, "universe_stale": True}
    assert i18n.t("part_stale") in re.sub(r"<[^>]+>", " ", _html(part=stale))


def test_failure_is_named_in_the_banner():
    """A breadth failure must be announced, not silently omitted."""
    degradation.reset()
    degradation.record("participation", RuntimeError("no S&P 500 constituent list available"))
    assert degradation.failures() == [("participation", "reason_data")], degradation.failures()
    text = re.sub(r"<[^>]+>", " ", _html(part=None, degradations=degradation.failures()))
    assert i18n.t("sec_participation") in text
    assert i18n.t("reason_data") in text
    degradation.reset()


def test_renders_in_both_languages():
    original = i18n.language()
    try:
        for lang in ("en", "zh"):
            i18n.set_language(lang)
            text = re.sub(r"<[^>]+>", " ", _html())
            assert i18n.t("sec_participation") in text, f"{lang}: missing header"
            assert i18n.t("part_short") in text, f"{lang}: missing horizon label"
            assert "{" not in text, f"{lang}: unsubstituted placeholder"
    finally:
        i18n.set_language(original)


if __name__ == "__main__":
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {fn.__name__}\n    {e}")
    sys.exit(1 if failures else 0)
