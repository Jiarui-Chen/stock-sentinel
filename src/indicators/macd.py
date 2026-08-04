from typing import Dict, List, Optional

import pandas as pd


def _detect_cross(hist_series: List[float], lookback: int) -> Optional[str]:
    """
    Returns 'bullish'/'bearish' if the histogram (MACD line − signal line) changed
    sign within the last `lookback` transitions, else None. If more than one flip
    occurs in the window, the most recent one wins.
    """
    if len(hist_series) < lookback + 1:
        return None
    window = hist_series[-(lookback + 1):]
    cross = None
    for prev, curr in zip(window, window[1:]):
        if prev <= 0 < curr:
            cross = "bullish"
        elif prev >= 0 > curr:
            cross = "bearish"
    return cross


def compute(df: pd.DataFrame, n: int = 60, cross_lookback: int = 3) -> Dict:
    """Returns MACD histogram (MACD line − signal line) sign and momentum direction for the latest bar,
    whether the MACD line itself sits above/below zero, whether a MACD/signal crossover happened within
    the last `cross_lookback` bars, plus the last n periods of MACD line, signal line, and histogram
    series for visualization."""
    close = df["Close"]
    if len(close) < 27:
        return {
            "histogram": None, "sign": None, "momentum": None,
            "macd_line_sign": None, "cross": None,
            "macd_series": [], "signal_series": [], "hist_series": [],
        }

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    current = float(histogram.iloc[-1])
    previous = float(histogram.iloc[-2])
    hist_series = [float(v) for v in histogram.iloc[-n:]]

    return {
        "histogram":      round(current, 4),
        "sign":           "positive" if current > 0 else "negative",
        "momentum":       "increasing" if current > previous else "decreasing",
        "macd_line_sign": "positive" if float(macd_line.iloc[-1]) > 0 else "negative",
        "cross":          _detect_cross(hist_series, cross_lookback),
        "macd_series":    [float(v) for v in macd_line.iloc[-n:]],
        "signal_series":  [float(v) for v in signal_line.iloc[-n:]],
        "hist_series":    hist_series,
    }
