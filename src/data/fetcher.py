import pandas as pd
from typing import Optional

from src.data.yf_session import ticker_scope


def _fetch(ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        with ticker_scope(ticker) as t:
            df = t.history(period=period, interval=interval)
        return df if not df.empty else None
    except Exception as e:
        print(f"[ERROR] {ticker} ({interval}): {e}")
        return None


def fetch_daily(ticker: str) -> Optional[pd.DataFrame]:
    return _fetch(ticker, period="3mo", interval="1d")


def fetch_weekly(ticker: str) -> Optional[pd.DataFrame]:
    return _fetch(ticker, period="2y", interval="1wk")
