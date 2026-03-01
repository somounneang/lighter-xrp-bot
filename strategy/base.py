"""
strategy/base.py
----------------
Abstract base class for all strategies.
Every strategy returns a Signal that the execution layer acts on.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum

import pandas as pd


class Direction(IntEnum):
    LONG  =  1
    FLAT  =  0
    SHORT = -1


@dataclass
class Signal:
    direction:    Direction   # LONG / SHORT / FLAT
    entry_price:  float       # Suggested limit price (0 = market)
    stop_loss:    float       # Absolute price level for stop-loss
    take_profit:  float       # Absolute price level for take-profit
    size_xrp:     float       # Raw XRP amount to trade (risk manager may clip)
    reason:       str = ""    # Human-readable explanation for logs


class BaseStrategy(ABC):

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, mid_price: float,
                        current_position: float, collateral: float) -> Signal:
        """
        Evaluate the latest candle data and account state, return a Signal.

        Args:
            df:                 OHLCV DataFrame (newest row = last)
            mid_price:          Current mid price
            current_position:   Signed XRP position (+ long, - short)
            collateral:         Free USDC collateral

        Returns:
            Signal
        """
        ...

    @property
    @abstractmethod
    def min_candles_required(self) -> int:
        """Minimum number of completed candles needed before trading."""
        ...
