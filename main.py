import json
import socket
import sys
import time
import schedule
from datetime import datetime, date, timedelta

from src.data import fetcher, news_fetcher, fundamentals_fetcher, earnings_fetcher, pre_earnings_fetcher
from src.indicators import rsi, rsi_divergence, macd, option_flow
from src.agent import analyzer, news_analyzer, sentinel_analyzer, earnings_analyzer, pre_earnings_analyzer
from src.report import email_reporter, earnings_reporter, pre_earnings_reporter
from src.config import REPORT_TIME, EARNINGS_EVENING_TIME, EARNINGS_MORNING_TIME


def load_watchlist() -> list[str]:
    with open("watchlist.json") as f:
        return json.load(f)["tickers"]


def _wait_for_network(timeout: int = 120) -> bool:
    """Block until finance.yahoo.com is reachable, or timeout (seconds) expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("finance.yahoo.com", 443), timeout=5)
            return True
        except OSError:
            time.sleep(10)
    return False


def run(force: bool = False) -> None:
    now = datetime.now()

    print(f"[{now:%Y-%m-%d %H:%M}] Starting daily run...")

    tickers = load_watchlist()
    active_tickers = []
    results = []
    macd_viz = {}
    for ticker in tickers:
        try:
            print(f"  [{ticker}] Fetching data...")
            daily_df = fetcher.fetch_daily(ticker)
            weekly_df = fetcher.fetch_weekly(ticker)
            if daily_df is None or daily_df.empty or weekly_df is None or weekly_df.empty:
                print(f"  [{ticker}] No price data returned — skipping.")
                continue
            daily_rsi = rsi.compute(daily_df)
            weekly_rsi = rsi.compute(weekly_df)
            daily_macd = macd.compute(daily_df)
            weekly_macd = macd.compute(weekly_df)
            results.append({
                "ticker": ticker,
                "daily_rsi": daily_rsi,
                "weekly_rsi": weekly_rsi,
                "daily_alert": rsi.classify(daily_rsi),
                "weekly_alert": rsi.classify(weekly_rsi),
                "daily_rsi_divergence": rsi_divergence.detect(daily_df, rsi_divergence._SWING_WINDOW_DAILY),
                "weekly_rsi_divergence": rsi_divergence.detect(weekly_df, rsi_divergence._SWING_WINDOW_WEEKLY),
                "daily_macd_hist_sign": daily_macd["sign"],
                "daily_macd_hist_momentum": daily_macd["momentum"],
                "weekly_macd_hist_sign": weekly_macd["sign"],
                "weekly_macd_hist_momentum": weekly_macd["momentum"],
            })
            macd_viz[ticker] = {
                "daily_macd_series":    daily_macd["macd_series"],
                "daily_signal_series":  daily_macd["signal_series"],
                "daily_hist_series":    daily_macd["hist_series"],
                "weekly_macd_series":   weekly_macd["macd_series"],
                "weekly_signal_series": weekly_macd["signal_series"],
                "weekly_hist_series":   weekly_macd["hist_series"],
            }
            active_tickers.append(ticker)
        except Exception as e:
            print(f"  [{ticker}] Fetch failed: {e} — skipping.")

    if not active_tickers:
        print(f"[{now:%Y-%m-%d %H:%M}] No tickers returned data — "
              "network may be unavailable. Aborting run without sending email.")
        return

    print("  Enriching with Claude...")
    enriched, _ = analyzer.enrich(results)

    print("  Fetching news and fundamentals...")
    ticker_articles = news_fetcher.fetch_all(active_tickers)
    fundamentals    = fundamentals_fetcher.fetch_all(active_tickers)

    active_count = sum(1 for arts in ticker_articles.values() if arts)
    print(f"  Analyzing news ({active_count} tickers with articles)...")
    twitter_insights = news_analyzer.analyze(ticker_articles)
    print(f"  News summarized for: {list(twitter_insights.keys()) or 'none'}")

    enriched = [
        {
            **r,
            **twitter_insights.get(r["ticker"], {}),
            **macd_viz.get(r["ticker"], {}),
            "earnings_date":   fundamentals.get(r["ticker"], {}).get("earnings_date"),
            "earnings_timing": fundamentals.get(r["ticker"], {}).get("earnings_timing"),
        }
        for r in enriched
    ]

    print("  Checking pre-earnings triggers...")
    for ticker in active_tickers:
        ed_str = fundamentals.get(ticker, {}).get("earnings_date")
        if not ed_str:
            continue
        try:
            days_until = (date.fromisoformat(ed_str) - date.today()).days
            if not (0 < days_until <= 3):
                continue
            if pre_earnings_fetcher.already_sent(ticker, ed_str):
                continue
            history = pre_earnings_fetcher.fetch_history(ticker)
            if not history:
                print(f"  [{ticker}] No pre-earnings history available.")
                continue
            financials   = earnings_fetcher.fetch_financials(ticker)
            news_articles = ticker_articles.get(ticker, [])
            watch_points  = pre_earnings_analyzer.analyze(ticker, history, financials, news_articles)
            pre_earnings_reporter.send(ticker, ed_str, history, watch_points)
            pre_earnings_fetcher.mark_sent(ticker, ed_str, watch_points)
        except Exception as e:
            print(f"  [{ticker}] Pre-earnings email failed: {e}")

    print("  Scanning option flow...")
    option_flow_findings = option_flow.scan_all(active_tickers)
    if option_flow_findings:
        print(f"  Option flow anomalies: {list(option_flow_findings.keys())}")
        option_flow.print_report(option_flow_findings)

    print("  Running Sentinel analysis...")
    analyst_picks = sentinel_analyzer.analyze(enriched, fundamentals, option_flow_findings)
    print(f"  Buy: {[p['ticker'] for p in analyst_picks.get('buy', [])]}  "
          f"Sell: {[p['ticker'] for p in analyst_picks.get('sell', [])]}")

    print("  Sending report...")
    email_reporter.send(enriched, analyst_picks, option_flow_findings)
    print(f"[{now:%Y-%m-%d %H:%M}] Done.")


def _send_earnings_for(tickers: list, earnings_dates: dict = None) -> None:
    """
    First-time send for each ticker.
    - Skips tickers already sent with a complete metrics table (prevents duplicate sends
      e.g. for BMO earners that run at morning AND evening check).
    - Always sends even when metrics are unavailable; records the gap so the morning
      retry knows to follow up.
    """
    for ticker in tickers:
        try:
            ed_str = (earnings_dates or {}).get(ticker)

            if ed_str and earnings_fetcher.already_sent_ok(ticker, ed_str):
                print(f"  [{ticker}] Already sent with metrics — skipping.")
                continue

            print(f"  [{ticker}] Fetching earnings report...")
            report = earnings_fetcher.fetch_earnings_report(ticker, earnings_date=ed_str)
            if not report:
                print(f"  [{ticker}] No EDGAR content found — skipping.")
                continue

            has_metrics  = report.get("financials") is not None
            watch_points = pre_earnings_fetcher.get_watch_points(ticker, ed_str)
            analysis     = earnings_analyzer.analyze(
                ticker, report.get("financials"), report["transcript"],
                watch_points=watch_points,
            )
            if not analysis:
                continue

            earnings_reporter.send(ticker, analysis, report.get("financials"), watch_points)

            if ed_str:
                earnings_fetcher.record_sent(ticker, ed_str, has_metrics)
            if not has_metrics:
                print(f"  [{ticker}] Metrics not yet available — morning retry scheduled.")

        except Exception as e:
            print(f"  [{ticker}] Earnings report failed: {e}")


def _retry_earnings_for(tickers: list, earnings_dates: dict) -> None:
    """
    Morning retry for tickers whose first email had no metrics table.
    Sends a follow-up email only if yfinance has now updated; abandons silently otherwise.
    """
    for ticker in tickers:
        try:
            ed_str = earnings_dates.get(ticker)
            print(f"  [{ticker}] Retry — checking if metrics are now available...")
            report = earnings_fetcher.fetch_earnings_report(ticker, earnings_date=ed_str)

            if not report or not report.get("financials"):
                print(f"  [{ticker}] Metrics still unavailable — retry abandoned.")
                # Mark has_metrics=True so we don't retry again tomorrow.
                if ed_str:
                    earnings_fetcher.record_sent(ticker, ed_str, True)
                continue

            watch_points = pre_earnings_fetcher.get_watch_points(ticker, ed_str)
            analysis     = earnings_analyzer.analyze(
                ticker, report["financials"], report["transcript"],
                watch_points=watch_points,
            )
            if analysis:
                earnings_reporter.send(ticker, analysis, report["financials"], watch_points)
            if ed_str:
                earnings_fetcher.record_sent(ticker, ed_str, True)

        except Exception as e:
            print(f"  [{ticker}] Retry failed: {e}")


def run_earnings(label: str = "", force_tickers: list = None) -> None:
    """
    Check watchlist for tickers that reported earnings today or yesterday.

    Two-pass logic:
      1. First send  — fires for any ticker due today/yesterday that hasn't been sent yet
                       (or was sent successfully with metrics already).
      2. Morning retry — fires for tickers whose previous evening email had no metrics table;
                         sends a follow-up only if yfinance has updated by now.

    Pass force_tickers to bypass date/state checks (for testing).
    """
    now = datetime.now()
    print(f"[{now:%Y-%m-%d %H:%M}] Earnings check ({label or 'scheduled'})...")

    if force_tickers:
        print(f"  Test mode — skipping date/state checks, running: {force_tickers}")
        _send_earnings_for(force_tickers)
        return

    tickers      = load_watchlist()
    fundamentals = fundamentals_fetcher.fetch_all(tickers)
    earnings_dates = {
        t: fundamentals[t]["earnings_date"]
        for t in tickers
        if fundamentals.get(t, {}).get("earnings_date")
    }

    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    # Tickers that were sent yesterday without a metrics table → morning retry.
    retry = earnings_fetcher.get_retry_tickers(for_date=yesterday_str)

    # Due tickers for a first-time send; exclude those already queued for retry
    # (they were already sent last night — the retry path handles the follow-up).
    retry_set = set(retry)
    due       = earnings_fetcher.watchlist_due_today(tickers, earnings_dates)
    first_time = [t for t in due if t not in retry_set]

    if not first_time and not retry:
        print("  No earnings due and no pending retries.")
        return

    if first_time:
        print(f"  First send: {first_time}")
        _send_earnings_for(first_time, earnings_dates=earnings_dates)

    if retry:
        print(f"  Morning retry (metrics check): {retry}")
        _retry_earnings_for(retry, earnings_dates)


schedule.every().day.at(REPORT_TIME).do(run)
schedule.every().day.at(EARNINGS_EVENING_TIME).do(run_earnings, label="evening")
schedule.every().day.at(EARNINGS_MORNING_TIME).do(run_earnings, label="morning")

if __name__ == "__main__":
    if "--now" in sys.argv:
        run(force=True)
        sys.exit(0)
    if "--earnings-now" in sys.argv:
        idx            = sys.argv.index("--earnings-now")
        force_tickers  = [t.upper() for t in sys.argv[idx + 1:] if not t.startswith("--")] or None
        run_earnings(label="manual", force_tickers=force_tickers)
        sys.exit(0)
    if "--pre-earnings-now" in sys.argv:
        idx           = sys.argv.index("--pre-earnings-now")
        force_tickers = [t.upper() for t in sys.argv[idx + 1:] if not t.startswith("--")]
        if not force_tickers:
            print("Usage: python3 main.py --pre-earnings-now TICKER [TICKER ...]")
            sys.exit(1)
        for ticker in force_tickers:
            history = pre_earnings_fetcher.fetch_history(ticker)
            if not history:
                print(f"[{ticker}] No pre-earnings history available.")
                continue
            fundamentals  = fundamentals_fetcher.fetch_all([ticker])
            ed_str        = fundamentals.get(ticker, {}).get("earnings_date") or "TBD"
            financials    = earnings_fetcher.fetch_financials(ticker)
            news_articles = news_fetcher.fetch_news(ticker)
            watch_points  = pre_earnings_analyzer.analyze(ticker, history, financials, news_articles)
            pre_earnings_reporter.send(ticker, ed_str, history, watch_points)
        sys.exit(0)

    print("Stock Sentinel starting — waiting for network...")
    if not _wait_for_network(timeout=120):
        print("[ERROR] Network unreachable after 120s — exiting. launchd will restart the process.")
        sys.exit(1)

    print(f"Stock Sentinel running — report at {REPORT_TIME}, "
          f"earnings checks at {EARNINGS_EVENING_TIME} and {EARNINGS_MORNING_TIME}.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f"[ERROR] Run failed: {e}")
        time.sleep(30)
