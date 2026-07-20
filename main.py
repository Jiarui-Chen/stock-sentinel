import json
import sys
import time
import schedule
from datetime import datetime

from src.data import fetcher, news_fetcher, fundamentals_fetcher, earnings_fetcher
from src.indicators import rsi, rsi_divergence, macd, option_flow
from src.agent import analyzer, news_analyzer, sentinel_analyzer, earnings_analyzer
from src.report import email_reporter, earnings_reporter
from src.config import REPORT_TIME, EARNINGS_EVENING_TIME, EARNINGS_MORNING_TIME


def load_watchlist() -> list[str]:
    with open("watchlist.json") as f:
        return json.load(f)["tickers"]


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


def _send_earnings_for(tickers: list, label: str, earnings_dates: dict = None) -> None:
    """Fetch press release + financials from EDGAR/yfinance and send one email per ticker."""
    for ticker in tickers:
        try:
            print(f"  [{ticker}] Fetching earnings report...")
            ed_str = (earnings_dates or {}).get(ticker)
            report = earnings_fetcher.fetch_earnings_report(ticker, earnings_date=ed_str)
            if not report:
                print(f"  [{ticker}] Transcript not available yet — will retry at next check.")
                continue
            analysis = earnings_analyzer.analyze(
                ticker,
                report.get("financials"),
                report["transcript"],
            )
            if not analysis:
                continue
            earnings_reporter.send(ticker, analysis, report.get("financials"))
        except Exception as e:
            print(f"  [{ticker}] Earnings report failed: {e}")


def run_earnings(label: str = "", force_tickers: list = None) -> None:
    """
    Check watchlist for tickers that reported earnings today or yesterday,
    then send one analysis email per ticker.

    Pass force_tickers to bypass the date check (for testing).
    """
    now = datetime.now()
    print(f"[{now:%Y-%m-%d %H:%M}] Earnings check ({label or 'scheduled'})...")

    if force_tickers:
        print(f"  Test mode — skipping date check, running: {force_tickers}")
        _send_earnings_for(force_tickers, label)
        return

    tickers      = load_watchlist()
    fundamentals = fundamentals_fetcher.fetch_all(tickers)
    earnings_dates = {
        t: fundamentals[t]["earnings_date"]
        for t in tickers
        if fundamentals.get(t, {}).get("earnings_date")
    }

    due = earnings_fetcher.watchlist_due_today(tickers, earnings_dates)
    if not due:
        print("  No earnings due today/yesterday.")
        return

    print(f"  Earnings due: {due}")
    _send_earnings_for(due, label, earnings_dates=earnings_dates)


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
    print(f"Stock Sentinel running — report at {REPORT_TIME}, "
          f"earnings checks at {EARNINGS_EVENING_TIME} and {EARNINGS_MORNING_TIME}.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f"[ERROR] Run failed: {e}")
        time.sleep(30)
