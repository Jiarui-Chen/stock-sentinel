from datetime import datetime, timedelta, timezone
from typing import Dict, List

import yfinance as yf


def fetch_tweets(ticker: str) -> List[str]:
    try:
        news = yf.Ticker(ticker).news or []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [
            n for n in news
            if datetime.fromtimestamp(
                (n.get("content") or {}).get("pubDate") and
                _parse_pubdate((n.get("content") or {}).get("pubDate")) or
                n.get("providerPublishTime", 0),
                tz=timezone.utc,
            ) >= cutoff
        ]
        titles = [
            (n.get("content") or {}).get("title") or n.get("title")
            for n in recent
        ]
        return [t for t in titles if t]
    except Exception as e:
        print(f"[WARN] News fetch failed for {ticker}: {e}")
        return []


def _parse_pubdate(pubdate: str) -> float:
    try:
        return datetime.fromisoformat(pubdate.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def fetch_all(tickers: List[str]) -> Dict[str, List[str]]:
    return {ticker: fetch_tweets(ticker) for ticker in tickers}
