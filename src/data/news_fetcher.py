from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TimeoutError
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import time

import yfinance as yf

_FETCH_TIMEOUT = 20   # seconds per attempt
_MAX_RETRIES   = 2    # retry once on timeout or network error
_RETRY_DELAY   = 2.0  # seconds between retries
_MAX_WORKERS   = 6    # concurrent requests — high enough to be fast, low enough to avoid rate-limiting


def fetch_news(ticker: str) -> List[Dict[str, str]]:
    for attempt in range(_MAX_RETRIES):
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: yf.Ticker(ticker).news or [])
                try:
                    news = future.result(timeout=_FETCH_TIMEOUT)
                except _TimeoutError:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_RETRY_DELAY)
                        continue
                    print(f"[WARN] [{ticker}] News fetch timed out after {_MAX_RETRIES} attempts — skipping.")
                    return []

            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            articles = []
            for n in news:
                content = n.get("content") or {}
                pub_ts  = _parse_pubdate(content.get("pubDate", "")) or n.get("providerPublishTime", 0)
                if datetime.fromtimestamp(pub_ts, tz=timezone.utc) < cutoff:
                    continue
                title   = content.get("title")   or n.get("title", "")
                summary = content.get("summary") or ""
                if title:
                    articles.append({"title": title, "summary": summary[:300]})
                if len(articles) == 8:
                    break
            return articles

        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)
                continue
            print(f"[WARN] [{ticker}] News fetch failed: {e}")
            return []
    return []


def _parse_pubdate(pubdate: str) -> float:
    try:
        return datetime.fromisoformat(pubdate.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def fetch_all(tickers: List[str]) -> Dict[str, List[Dict[str, str]]]:
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {ticker: executor.submit(fetch_news, ticker) for ticker in tickers}
        return {ticker: f.result() for ticker, f in futures.items()}
