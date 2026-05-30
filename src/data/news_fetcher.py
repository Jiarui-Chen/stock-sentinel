from datetime import datetime, timedelta, timezone
from typing import Dict, List

import yfinance as yf


def fetch_news(ticker: str) -> List[Dict[str, str]]:
    try:
        news = yf.Ticker(ticker).news or []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles = []
        for n in news:
            content = n.get("content") or {}
            pub_ts = _parse_pubdate(content.get("pubDate", "")) or n.get("providerPublishTime", 0)
            if datetime.fromtimestamp(pub_ts, tz=timezone.utc) < cutoff:
                continue
            title   = content.get("title")   or n.get("title", "")
            summary = content.get("summary") or ""
            if title:
                articles.append({"title": title, "summary": summary[:300]})
            if len(articles) == 5:
                break
        return articles
    except Exception as e:
        print(f"[WARN] News fetch failed for {ticker}: {e}")
        return []


def _parse_pubdate(pubdate: str) -> float:
    try:
        return datetime.fromisoformat(pubdate.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def fetch_all(tickers: List[str]) -> Dict[str, List[Dict[str, str]]]:
    return {ticker: fetch_news(ticker) for ticker in tickers}
