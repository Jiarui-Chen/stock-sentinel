import json
import sys
import time
import schedule
from datetime import datetime

from src.data import fetcher, news_fetcher, fundamentals_fetcher
from src.indicators import rsi, rsi_divergence, macd, option_flow
from src.agent import analyzer, news_analyzer, sentinel_analyzer
from src.report import email_reporter
from src.config import REPORT_TIME


def load_watchlist() -> list[str]:
    with open("watchlist.json") as f:
        return json.load(f)["tickers"]


def run(force: bool = False) -> None:
    now = datetime.now()

    print(f"[{now:%Y-%m-%d %H:%M}] Starting daily run...")

    tickers = load_watchlist()
    results = []
    macd_viz = {}
    for ticker in tickers:
        print(f"  [{ticker}] Fetching data...")
        daily_df = fetcher.fetch_daily(ticker)
        weekly_df = fetcher.fetch_weekly(ticker)
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
            "daily_macd_series":   daily_macd["macd_series"],
            "daily_signal_series": daily_macd["signal_series"],
            "daily_hist_series":   daily_macd["hist_series"],
            "weekly_macd_series":   weekly_macd["macd_series"],
            "weekly_signal_series": weekly_macd["signal_series"],
            "weekly_hist_series":   weekly_macd["hist_series"],
        }

    print("  Enriching with Claude...")
    enriched, _ = analyzer.enrich(results)

    print("  Fetching news and fundamentals...")
    ticker_articles = news_fetcher.fetch_all(tickers)
    fundamentals    = fundamentals_fetcher.fetch_all(tickers)

    active_count = sum(1 for arts in ticker_articles.values() if arts)
    print(f"  Analyzing news ({active_count} tickers with articles)...")
    twitter_insights = news_analyzer.analyze(ticker_articles)
    print(f"  News summarized for: {list(twitter_insights.keys()) or 'none'}")

    enriched = [
        {**r, **twitter_insights.get(r["ticker"], {}), **macd_viz.get(r["ticker"], {})}
        for r in enriched
    ]

    print("  Scanning option flow...")
    option_flow_findings = option_flow.scan_all(tickers)
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


schedule.every().day.at(REPORT_TIME).do(run)

if __name__ == "__main__":
    if "--now" in sys.argv:
        run(force=True)
        sys.exit(0)
    print(f"Stock Sentinel running — report scheduled at {REPORT_TIME} on weekdays.")
    while True:
        schedule.run_pending()
        time.sleep(30)
