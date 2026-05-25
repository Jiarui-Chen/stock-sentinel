import pandas as pd
from typing import Optional
from src.config import RSI_PERIOD, RSI_WATCH_THRESHOLD, RSI_BUY_THRESHOLD


def compute(df: Optional[pd.DataFrame]) -> Optional[float]:
    if df is None or len(df) < RSI_PERIOD + 1:
        return None
    closes = df["Close"].dropna()
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing
    avg_gain = gain.ewm(alpha=1 / RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(alpha=1 / RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def classify(rsi: Optional[float]) -> Optional[str]:
    if rsi is None:
        return None
    if rsi < RSI_BUY_THRESHOLD:
        return "consider_buy"
    if rsi < RSI_WATCH_THRESHOLD:
        return "watch"
    return None
