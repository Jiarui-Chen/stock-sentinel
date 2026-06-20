from typing import Dict

import pandas as pd


def compute(df: pd.DataFrame, n: int = 60) -> Dict:
    """Returns MACD histogram (MACD line − signal line) sign and momentum direction for the latest bar,
    plus the last n periods of MACD line, signal line, and histogram series for visualization."""
    close = df["Close"]
    if len(close) < 27:
        return {
            "histogram": None, "sign": None, "momentum": None,
            "macd_series": [], "signal_series": [], "hist_series": [],
        }

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    current = float(histogram.iloc[-1])
    previous = float(histogram.iloc[-2])

    return {
        "histogram":     round(current, 4),
        "sign":          "positive" if current > 0 else "negative",
        "momentum":      "increasing" if current > previous else "decreasing",
        "macd_series":   [float(v) for v in macd_line.iloc[-n:]],
        "signal_series": [float(v) for v in signal_line.iloc[-n:]],
        "hist_series":   [float(v) for v in histogram.iloc[-n:]],
    }
