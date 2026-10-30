"""
Pattern Utility Functions
Shared helpers for swing point detection, trendline fitting, volume analysis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from scipy.stats import linregress


def find_swing_highs(df: pd.DataFrame, window: int = 5) -> np.ndarray:
    """Return indices of local swing-high bars."""
    highs = df["high"].values
    idx = argrelextrema(highs, np.greater_equal, order=window)[0]
    return idx


def find_swing_lows(df: pd.DataFrame, window: int = 5) -> np.ndarray:
    """Return indices of local swing-low bars."""
    lows = df["low"].values
    idx = argrelextrema(lows, np.less_equal, order=window)[0]
    return idx


def pct_diff(a: float, b: float) -> float:
    """Absolute percentage difference between two prices."""
    if b == 0:
        return float("inf")
    return abs(a - b) / b


def prices_approx_equal(a: float, b: float, tol: float = 0.003) -> bool:
    return pct_diff(a, b) <= tol


def fit_trendline(x: np.ndarray, y: np.ndarray):
    """Return (slope, intercept, r_value) from linear regression."""
    if len(x) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0, 0.0
    slope, intercept, r, *_ = linregress(x, y)
    return slope, intercept, r


def volume_spike(df: pd.DataFrame, idx: int, period: int = 20, mult: float = 1.3) -> bool:
    """True if volume at `idx` is >= mult × average of prior `period` bars."""
    if idx < period:
        return True  # not enough history, accept
    avg_vol = df["volume"].iloc[idx - period: idx].mean()
    if avg_vol == 0:
        return True
    return df["volume"].iloc[idx] >= avg_vol * mult


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"]  - df["close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def rolling_slope(series: pd.Series, window: int = 10) -> pd.Series:
    """Rolling linear regression slope normalised by price."""
    slopes = []
    arr = series.values
    for i in range(len(arr)):
        if i < window - 1:
            slopes.append(np.nan)
        else:
            y = arr[i - window + 1: i + 1]
            x = np.arange(window)
            s, *_ = linregress(x, y)
            slopes.append(s / arr[i] if arr[i] != 0 else 0)
    return pd.Series(slopes, index=series.index)
