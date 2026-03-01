"""
strategy/indicators.py
----------------------
Pure-function technical indicators computed on a pandas DataFrame.
All functions accept a DataFrame with at least ['close'] (and
optionally ['high', 'low']) columns and return a pandas Series.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# ── Trend indicators ──────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def ema_crossover_signal(df: pd.DataFrame, fast: int, slow: int) -> int:
    """
    Returns:
        +1  if fast EMA just crossed above slow EMA (bullish)
        -1  if fast EMA just crossed below slow EMA (bearish)
         0  no crossover on latest bar
    """
    closes   = df["close"]
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)

    if len(fast_ema) < 2:
        return 0

    prev_diff = fast_ema.iloc[-2] - slow_ema.iloc[-2]
    curr_diff = fast_ema.iloc[-1] - slow_ema.iloc[-1]

    if prev_diff <= 0 < curr_diff:
        return 1      # Golden cross
    if prev_diff >= 0 > curr_diff:
        return -1     # Death cross
    return 0


def trend_direction(df: pd.DataFrame, fast: int, slow: int) -> int:
    """
    Returns current trend direction without requiring a fresh crossover:
        +1  fast above slow (uptrend)
        -1  fast below slow (downtrend)
    """
    closes   = df["close"]
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    diff = fast_ema.iloc[-1] - slow_ema.iloc[-1]
    return 1 if diff > 0 else -1


# ── Momentum indicators ───────────────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing via EWM)."""
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def current_rsi(df: pd.DataFrame, period: int = 14) -> float:
    return float(rsi(df["close"], period).iloc[-1])


# ── Volatility indicators ─────────────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high  = df["high"]
    low   = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def current_atr(df: pd.DataFrame, period: int = 14) -> float:
    return float(atr(df, period).iloc[-1])


# ── Mean-reversion indicators ─────────────────────────────────────────────────

def bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> dict:
    """
    Returns {"mid": Series, "upper": Series, "lower": Series, "width": Series}
    """
    mid    = df["close"].rolling(period).mean()
    std    = df["close"].rolling(period).std()
    upper  = mid + std_dev * std
    lower  = mid - std_dev * std
    width  = (upper - lower) / mid   # normalised band width
    return {"mid": mid, "upper": upper, "lower": lower, "width": width}


def bb_signal(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0,
              min_width: float = 0.005) -> int:
    """
    Returns:
        +1  price crossed above lower band (mean-reversion buy)
        -1  price crossed below upper band (mean-reversion sell)
         0  no signal or bands too tight
    """
    bb = bollinger_bands(df, period, std_dev)
    if float(bb["width"].iloc[-1]) < min_width:
        return 0  # Squeeze — avoid trading in flat markets

    close = df["close"]
    prev  = close.iloc[-2]
    curr  = close.iloc[-1]
    lower = bb["lower"].iloc[-1]
    upper = bb["upper"].iloc[-1]

    if prev < lower and curr > lower:
        return 1   # Bounce from lower band → buy
    if prev > upper and curr < upper:
        return -1  # Rejection from upper band → sell
    return 0
