"""
market/candles.py
-----------------
Maintains an in-memory rolling price history and synthesises 1-minute
pseudo-candles from mid-price samples.  The strategy modules consume
this to compute EMA, RSI, ATR, Bollinger Bands.

Since Lighter's public API doesn't expose a candle endpoint in the SDK
yet, we build candles from sampled mid-prices polled every
POLL_INTERVAL_SECONDS.  For higher-frequency strategies, replace
`record_price()` with a WebSocket tick handler.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

# How many candles to keep in memory (e.g. 200 is enough for any indicator)
MAX_CANDLES = 300


@dataclass
class Candle:
    ts: float    # Unix timestamp of candle open
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class CandleBuffer:
    """
    Collects raw price samples and emits completed candles at a
    configurable interval (default: 60 s).
    """

    def __init__(self, interval_seconds: int = 60):
        self._interval = interval_seconds
        self._candles: deque[Candle] = deque(maxlen=MAX_CANDLES)
        self._open_ts: float | None = None
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._last: float | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def record_price(self, price: float, ts: float | None = None) -> bool:
        """
        Ingest a new price sample.  Returns True if a candle was completed.
        """
        now = ts or time.time()

        # First sample ever
        if self._open_ts is None:
            self._start_candle(price, now)
            return False

        elapsed = now - self._open_ts

        if elapsed >= self._interval:
            # Close the current candle
            self._candles.append(Candle(
                ts=self._open_ts,
                open=self._open,
                high=self._high,
                low=self._low,
                close=self._last,
            ))
            log.debug(f"Candle closed: O={self._open:.4f} H={self._high:.4f} "
                      f"L={self._low:.4f} C={self._last:.4f}")
            self._start_candle(price, now)
            return True

        # Update current candle
        self._high = max(self._high, price)
        self._low  = min(self._low,  price)
        self._last = price
        return False

    def to_dataframe(self) -> pd.DataFrame:
        """Return a DataFrame of completed candles (newest last)."""
        if not self._candles:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        return pd.DataFrame(list(self._candles))

    def enough_data(self, min_candles: int) -> bool:
        return len(self._candles) >= min_candles

    def __len__(self) -> int:
        return len(self._candles)

    # ── Private ───────────────────────────────────────────────────────────────

    def _start_candle(self, price: float, ts: float) -> None:
        self._open_ts = ts
        self._open = self._high = self._low = self._last = price


# Module-level singleton used by the strategy layer
_buffer: CandleBuffer | None = None


def get_candle_buffer(interval_seconds: int = 60) -> CandleBuffer:
    global _buffer
    if _buffer is None:
        _buffer = CandleBuffer(interval_seconds=interval_seconds)
        log.info(f"CandleBuffer created (interval={interval_seconds}s)")
    return _buffer
