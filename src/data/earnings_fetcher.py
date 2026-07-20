"""
Fetches earnings call transcripts from SEC EDGAR (free, no API key required)
and financial metrics from yfinance.

EDGAR notes:
- Companies file earnings call transcripts as exhibits to 8-K filings,
  typically under Item 7.01 (Reg FD) or 9.01 (Financial Statements & Exhibits).
- Not every company files a verbatim transcript — those that don't will return None.
- EDGAR requests ≤ 10/sec; we sleep 110ms between calls to stay compliant.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yfinance as yf

# ── Send-state helpers ────────────────────────────────────────────────────────
# Tracks which tickers were sent and whether they included a metrics table,
# so the scheduler can (a) avoid duplicate sends and (b) trigger a morning retry.

_STATE_FILE = Path(__file__).resolve().parents[2] / "logs" / "earnings_state.json"


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


def record_sent(ticker: str, earnings_date: str, has_metrics: bool) -> None:
    """Record that we sent an email for this ticker's earnings."""
    state = _load_state()
    state[ticker] = {"date": earnings_date, "has_metrics": has_metrics}
    _save_state(state)


def already_sent_ok(ticker: str, earnings_date: str) -> bool:
    """True if we already sent a complete email (with metrics) for this earnings date."""
    entry = _load_state().get(ticker)
    return bool(entry and entry.get("date") == earnings_date and entry.get("has_metrics"))


def get_retry_tickers(for_date: str) -> List[str]:
    """Tickers whose first email on for_date was sent without a metrics table."""
    return [
        t for t, v in _load_state().items()
        if v.get("date") == for_date and not v.get("has_metrics", True)
    ]

_EDGAR_BASE    = "https://www.sec.gov"
_DATA_BASE     = "https://data.sec.gov"
_HEADERS       = {
    "User-Agent": "StockSentinel research@stocksentinel.local",
    "Accept-Encoding": "gzip, deflate",
}
_TIMEOUT       = 15
_LOOKBACK_DAYS = 90   # how far back to search for the latest transcript

_cik_cache: Dict[str, str] = {}


# ── EDGAR helpers ─────────────────────────────────────────────────────────────

def _edgar_get(url: str) -> requests.Response:
    time.sleep(0.11)   # stay under the 10 req/sec EDGAR limit
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return r


def _get_cik(ticker: str) -> Optional[str]:
    global _cik_cache
    if not _cik_cache:
        data = _edgar_get(f"{_EDGAR_BASE}/files/company_tickers.json").json()
        _cik_cache = {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in data.values()
        }
    return _cik_cache.get(ticker.upper())


def _get_recent_8ks(cik: str) -> List[Dict]:
    data   = _edgar_get(f"{_DATA_BASE}/submissions/CIK{cik}.json").json()
    recent = data["filings"]["recent"]
    cutoff = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    return [
        {"date": filed, "accession": acc}
        for form, filed, acc in zip(
            recent["form"], recent["filingDate"], recent["accessionNumber"]
        )
        if form in ("8-K", "8-K/A") and filed >= cutoff
    ]


def _get_filing_docs(cik: str, accession: str) -> List[Dict]:
    """Parse the HTML filing index and return documents with url + description."""
    cik_int = int(cik)
    acc_nd  = accession.replace("-", "")
    url     = f"{_EDGAR_BASE}/Archives/edgar/data/{cik_int}/{acc_nd}/{accession}-index.htm"
    try:
        html = _edgar_get(url).text
    except Exception:
        return []

    docs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE):
        href = re.search(r'href="([^"]+\.(htm|html|txt))"', row, re.IGNORECASE)
        if not href:
            continue
        path = href.group(1)
        if not path.startswith("http"):
            path = f"{_EDGAR_BASE}{path}"
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        desc  = re.sub(r"<[^>]+>", "", cells[1]).strip() if len(cells) > 1 else ""
        docs.append({"url": path, "description": desc})
    return docs


def _is_transcript(description: str, url: str) -> bool:
    text = (description + " " + url).lower()
    return "transcript" in text


def _is_press_release(description: str, url: str) -> bool:
    """Match Exhibit 99.1 press-release documents."""
    desc  = description.strip().upper()
    lower = (description + " " + url).lower()
    return desc in ("EX-99.1", "EX-991", "EXHIBIT 99.1") or (
        "ex-99.1" in lower or "ex99_1" in lower or "ex991" in lower
        or "press release" in lower
    )


def _clean_html(html: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    for ent, rep in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                     ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(ent, rep)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Financial metrics via yfinance ────────────────────────────────────────────

def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _pct_change(cur, prev) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def _pp_change(cur, prev) -> Optional[float]:
    """Percentage-point difference — used for margins, not % change."""
    if cur is None or prev is None:
        return None
    return round(cur - prev, 1)


# ── Public API ────────────────────────────────────────────────────────────────

def _fetch_doc(url: str) -> Optional[str]:
    try:
        text = _clean_html(_edgar_get(url).text)
        return text if len(text) > 1000 else None
    except Exception:
        return None


def fetch_transcript(ticker: str) -> Optional[str]:
    """
    Search recent EDGAR 8-K filings for earnings content.

    Priority:
      1. A dedicated transcript exhibit (companies that file verbatim transcripts)
      2. The EX-99.1 press release (always filed — contains management commentary,
         financial highlights, and guidance language used for the analysis)

    Returns plain text or None if nothing is found.
    """
    try:
        cik = _get_cik(ticker)
        if not cik:
            print(f"[WARN] [{ticker}] Not found in EDGAR company list.")
            return None

        filings = _get_recent_8ks(cik)
        if not filings:
            print(f"[WARN] [{ticker}] No 8-K filings on EDGAR in the last {_LOOKBACK_DAYS} days.")
            return None

        press_release_fallback: Optional[str] = None
        press_release_date: str = ""

        for filing in filings:
            docs = _get_filing_docs(cik, filing["accession"])

            # Pass 1: prefer a verbatim transcript exhibit
            for doc in docs:
                if _is_transcript(doc["description"], doc["url"]):
                    text = _fetch_doc(doc["url"])
                    if text:
                        print(f"  [{ticker}] EDGAR transcript found "
                              f"({len(text):,} chars, filed {filing['date']})")
                        return text

            # Pass 2: capture the press release as fallback (first filing only)
            if press_release_fallback is None:
                for doc in docs:
                    if _is_press_release(doc["description"], doc["url"]):
                        text = _fetch_doc(doc["url"])
                        if text:
                            press_release_fallback = text
                            press_release_date = filing["date"]
                            break

        if press_release_fallback:
            print(f"  [{ticker}] Using EDGAR earnings press release "
                  f"({len(press_release_fallback):,} chars, filed {press_release_date})")
            return press_release_fallback

        print(f"[WARN] [{ticker}] No earnings content found in EDGAR 8-Ks "
              f"(last {_LOOKBACK_DAYS} days).")
        return None

    except Exception as e:
        print(f"[WARN] [{ticker}] EDGAR fetch failed: {e}")
        return None


def fetch_financials(ticker: str, expected_period: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches quarterly income statement via yfinance and computes QoQ / YoY deltas.

    expected_period: if provided, warns when yfinance's most-recent quarter end date
    is more than 45 days earlier (indicates data hasn't updated yet after the call).
    The caller can treat the return value as stale and omit it from the email.
    """
    try:
        df = yf.Ticker(ticker).quarterly_income_stmt
        if df is None or df.empty or df.shape[1] < 2:
            return None

        cols = df.columns  # most-recent quarter first

        # Staleness check: yfinance often lags 1-3 days after the earnings call.
        # If the most-recent period end is suspiciously old relative to today, flag it.
        if hasattr(cols[0], "date"):
            most_recent = cols[0].date()
        elif hasattr(cols[0], "strftime"):
            most_recent = cols[0].to_pydatetime().date()
        else:
            most_recent = None

        if most_recent and expected_period and (expected_period - most_recent).days > 45:
            print(f"  [{ticker}] yfinance financials lag detected: "
                  f"most recent quarter ends {most_recent}, expected near {expected_period}. "
                  f"Metrics table will be omitted — EDGAR press release has the current numbers.")
            return None

        def val(col_idx: int, row: str) -> Optional[float]:
            return _safe(df[cols[col_idx]].get(row)) if col_idx < df.shape[1] else None

        rev  = val(0, "Total Revenue");    prev_rev = val(1, "Total Revenue");    yoy_rev = val(4, "Total Revenue")
        gp   = val(0, "Gross Profit");     prev_gp  = val(1, "Gross Profit");     yoy_gp  = val(4, "Gross Profit")
        oi   = val(0, "Operating Income"); prev_oi  = val(1, "Operating Income"); yoy_oi  = val(4, "Operating Income")
        ni   = val(0, "Net Income");       prev_ni  = val(1, "Net Income");       yoy_ni  = val(4, "Net Income")

        def margin(num, den): return round(num / den * 100, 1) if num and den else None

        gm       = margin(gp,   rev);      prev_gm  = margin(prev_gp, prev_rev); yoy_gm  = margin(yoy_gp, yoy_rev)
        op_m     = margin(oi,   rev);      prev_op_m = margin(prev_oi, prev_rev); yoy_op_m = margin(yoy_oi, yoy_rev)

        # EPS derived from net income / diluted shares
        def eps_from(ni_val, col_idx):
            sh = val(col_idx, "Diluted Average Shares")
            return round(ni_val / sh, 2) if ni_val and sh else None

        eps      = eps_from(ni,      0)
        prev_eps = eps_from(prev_ni, 1)
        yoy_eps  = eps_from(yoy_ni,  4)

        period = cols[0].strftime("%Y-%m-%d") if hasattr(cols[0], "strftime") else str(cols[0])

        return {
            "period":           period,
            "revenue":          rev,
            "revenue_qoq":      _pct_change(rev, prev_rev),
            "revenue_yoy":      _pct_change(rev, yoy_rev),
            "gross_margin":     gm,
            "gross_margin_qoq": _pp_change(gm, prev_gm),
            "gross_margin_yoy": _pp_change(gm, yoy_gm),
            "op_margin":        op_m,
            "op_margin_qoq":    _pp_change(op_m, prev_op_m),
            "op_margin_yoy":    _pp_change(op_m, yoy_op_m),
            "net_income":       ni,
            "net_income_qoq":   _pct_change(ni, prev_ni),
            "net_income_yoy":   _pct_change(ni, yoy_ni),
            "eps":              eps,
            "eps_qoq":          _pct_change(eps, prev_eps),
            "eps_yoy":          _pct_change(eps, yoy_eps),
        }

    except Exception as e:
        print(f"[WARN] [{ticker}] Financials fetch failed: {e}")
        return None


def fetch_earnings_report(ticker: str, earnings_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches earnings press release / transcript (EDGAR) + financials (yfinance).
    Returns None if no EDGAR content is found.

    earnings_date: ISO date string (YYYY-MM-DD) of the earnings call, used to detect
    whether yfinance's income statement has already updated to the new quarter.
    """
    transcript = fetch_transcript(ticker)
    if not transcript:
        return None
    expected = None
    if earnings_date:
        try:
            expected = date.fromisoformat(earnings_date)
        except ValueError:
            pass
    return {"ticker": ticker, "transcript": transcript, "financials": fetch_financials(ticker, expected)}


def watchlist_due_today(tickers: List[str], earnings_dates: Dict[str, str]) -> List[str]:
    """Returns tickers whose earnings date was today or yesterday."""
    today, yesterday = date.today(), date.today() - timedelta(days=1)
    due = []
    for t in tickers:
        try:
            ed = date.fromisoformat(earnings_dates[t])
            if ed in (today, yesterday):
                due.append(t)
        except (KeyError, ValueError):
            continue
    return due
