import json
import sys
import time
import schedule
from datetime import datetime

from src.data import fetcher
from src.indicators import rsi, rsi_divergence
from src.agent import analyzer
from src.report import email_reporter
from src.config import REPORT_TIME


def load_watchlist() -> list[str]:
    with open("watchlist.json") as f:
        return json.load(f)["tickers"]


def run() -> None:
    now = datetime.now()
    if now.weekday() >= 5:
        print(f"[{now:%Y-%m-%d}] Weekend — skipping.")
        return

    print(f"[{now:%Y-%m-%d %H:%M}] Starting daily run...")

    tickers = load_watchlist()
    results = []
    for ticker in tickers:
        print(f"  [{ticker}] Fetching data...")
        daily_df = fetcher.fetch_daily(ticker)
        weekly_df = fetcher.fetch_weekly(ticker)
        daily_rsi = rsi.compute(daily_df)
        weekly_rsi = rsi.compute(weekly_df)
        results.append({
            "ticker": ticker,
            "daily_rsi": daily_rsi,
            "weekly_rsi": weekly_rsi,
            "daily_alert": rsi.classify(daily_rsi),
            "weekly_alert": rsi.classify(weekly_rsi),
            "daily_rsi_divergence": rsi_divergence.detect(daily_df, rsi_divergence._SWING_WINDOW_DAILY),
            "weekly_rsi_divergence": rsi_divergence.detect(weekly_df, rsi_divergence._SWING_WINDOW_WEEKLY),
        })

    print("  Enriching with Claude...")
    enriched, summary = analyzer.enrich(results)

    print("  Sending report...")
    email_reporter.send(enriched, summary)
    print(f"[{now:%Y-%m-%d %H:%M}] Done.")


schedule.every().day.at(REPORT_TIME).do(run)

if __name__ == "__main__":
    if "--now" in sys.argv:
        run()
        sys.exit(0)
    print(f"Stock Sentinel running — report scheduled at {REPORT_TIME} on weekdays.")
    while True:
        schedule.run_pending()
        time.sleep(30)
