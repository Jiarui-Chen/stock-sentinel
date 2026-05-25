import pandas as pd
from typing import Optional
from src.indicators.rsi import series as rsi_series
from src.config import RSI_PERIOD

_SWING_WINDOW_DAILY  = 3   # days on each side to confirm a swing point
_SWING_WINDOW_WEEKLY = 2   # weeks on each side to confirm a swing point
_LOOKBACK = 60             # max candles to search for divergence


def _swing_lows(prices: pd.Series, window: int) -> list[int]:
    result = []
    for i in range(window, len(prices) - window):
        if prices.iloc[i] == prices.iloc[i - window: i + window + 1].min():
            result.append(i)
    return result


def _swing_highs(prices: pd.Series, window: int) -> list[int]:
    result = []
    for i in range(window, len(prices) - window):
        if prices.iloc[i] == prices.iloc[i - window: i + window + 1].max():
            result.append(i)
    return result


def detect(df: Optional[pd.DataFrame], swing_window: int) -> Optional[str]:
    """
    Returns 'bullish', 'bearish', or None.

    Bullish:  price lower low + RSI higher low  (weakening downside momentum)
    Bearish:  price higher high + RSI lower high (weakening upside momentum)
    """
    min_candles = RSI_PERIOD + swing_window * 2 + 2
    if df is None or len(df) < min_candles:
        return None

    rsi = rsi_series(df)
    if rsi is None:
        return None

    df_w = df.iloc[-_LOOKBACK:].reset_index(drop=True)
    rsi_w = rsi.iloc[-_LOOKBACK:].reset_index(drop=True)

    lows = _swing_lows(df_w["Low"], swing_window)
    highs = _swing_highs(df_w["High"], swing_window)

    # Bullish divergence: price lower low, RSI higher low
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if df_w["Low"].iloc[i2] < df_w["Low"].iloc[i1] and rsi_w.iloc[i2] > rsi_w.iloc[i1]:
            return "bullish"

    # Bearish divergence: price higher high, RSI lower high
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if df_w["High"].iloc[i2] > df_w["High"].iloc[i1] and rsi_w.iloc[i2] < rsi_w.iloc[i1]:
            return "bearish"

    return None
