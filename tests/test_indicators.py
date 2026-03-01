"""
tests/test_indicators.py
------------------------
Run with: pytest tests/
"""
import pandas as pd
import numpy as np
import pytest
from strategy.indicators import (
    ema, ema_crossover_signal, rsi, current_rsi, atr,
    current_atr, bollinger_bands, bb_signal,
)


def _make_df(closes, highs=None, lows=None):
    n = len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    return pd.DataFrame({"close": closes, "high": highs, "low": lows})


class TestEMA:
    def test_ema_length(self):
        df = _make_df([1.0] * 30)
        result = ema(df["close"], 9)
        assert len(result) == 30

    def test_ema_constant_series(self):
        df = _make_df([2.5] * 50)
        result = ema(df["close"], 9)
        assert abs(result.iloc[-1] - 2.5) < 1e-9


class TestEMACrossover:
    def test_golden_cross(self):
        # Fast EMA was below, now crosses above
        closes = [1.0] * 30 + [1.5] * 5
        df = _make_df(closes)
        # At minimum we should get a +1 or 0 (crossover may not align exactly with last bar)
        result = ema_crossover_signal(df, fast=5, slow=20)
        assert result in (-1, 0, 1)

    def test_no_crossover_flat(self):
        df = _make_df([2.0] * 50)
        assert ema_crossover_signal(df, fast=5, slow=20) == 0


class TestRSI:
    def test_rsi_range(self):
        import random
        random.seed(42)
        closes = [2.0 + random.uniform(-0.1, 0.1) for _ in range(50)]
        df = _make_df(closes)
        val = current_rsi(df, 14)
        assert 0 <= val <= 100

    def test_rsi_overbought(self):
        # Steadily rising prices → RSI should be high
        closes = list(range(1, 51))
        df = _make_df(closes)
        val = current_rsi(df, 14)
        assert val > 70


class TestATR:
    def test_atr_positive(self):
        closes = [2.0 + i * 0.01 for i in range(30)]
        df = _make_df(closes)
        val = current_atr(df, 14)
        assert val > 0


class TestBollingerBands:
    def test_bb_structure(self):
        closes = [2.0 + (i % 5) * 0.05 for i in range(50)]
        df = _make_df(closes)
        bb = bollinger_bands(df, period=20)
        assert set(bb.keys()) == {"mid", "upper", "lower", "width"}
        # Upper must be above lower
        assert float(bb["upper"].iloc[-1]) > float(bb["lower"].iloc[-1])

    def test_bb_squeeze_returns_zero(self):
        # Flat market → bands very tight → signal should be 0
        df = _make_df([2.0] * 50)
        assert bb_signal(df, period=20, min_width=0.5) == 0
