import pandas as pd
from typing import Optional
from src.config import RSI_PERIOD, RSI_STRONG_BUY_THRESHOLD, RSI_BUY_THRESHOLD, RSI_WATCH_THRESHOLD, RSI_WARN_THRESHOLD, RSI_SELL_THRESHOLD, RSI_STRONG_SELL_THRESHOLD


def series(df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
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
    return 100 - (100 / (1 + rs))


def compute(df: Optional[pd.DataFrame]) -> Optional[float]:
    rsi = series(df)
    if rsi is None:
        return None
    return round(float(rsi.iloc[-1]), 2)


def classify(rsi: Optional[float]) -> Optional[str]:
    if rsi is None:
        return None
    if rsi < RSI_STRONG_BUY_THRESHOLD:
        return "strong_buy"
    if rsi < RSI_BUY_THRESHOLD:
        return "consider_buy"
    if rsi < RSI_WATCH_THRESHOLD:
        return "watch"
    if rsi >= RSI_STRONG_SELL_THRESHOLD:
        return "strong_sell"
    if rsi >= RSI_SELL_THRESHOLD:
        return "consider_sell"
    if rsi >= RSI_WARN_THRESHOLD:
        return "warn"
    return None
