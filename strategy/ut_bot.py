"""
strategy/ut_bot.py
------------------
UT Bot Alert Strategy

Logic:
  1. Compute ATR(atr_period) × key_value → trailing distance
  2. Trail a stop line that only moves in price direction
  3. BUY  when price crosses ABOVE the trail
  4. SELL when price crosses BELOW the trail
  5. EMA-200 filter: only LONG above EMA-200, SHORT below

.env parameters:
  UT_ATR_PERIOD = 10    (ATR lookback)
  UT_KEY_VALUE  = 1.5   (trail multiplier — higher = fewer signals)
  UT_EMA_FILTER = 200   (trend filter period)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import settings
from strategy.base import BaseStrategy, Direction, Signal
from strategy.indicators import ema, atr as atr_series, current_atr
from utils.logger import get_logger

log = get_logger(__name__)


def compute_ut_trail(df: pd.DataFrame, atr_period: int, key_value: float) -> pd.Series:
    """Compute the UT Bot ATR trailing stop line."""
    close    = df["close"].values
    atr_vals = atr_series(df, atr_period).values
    trail    = np.zeros(len(close))
    trail[0] = close[0]

    for i in range(1, len(close)):
        a      = atr_vals[i] * key_value
        prev_t = trail[i - 1]
        c      = close[i]
        pc     = close[i - 1]

        if c > prev_t and pc > prev_t:
            trail[i] = max(prev_t, c - a)
        elif c < prev_t and pc < prev_t:
            trail[i] = min(prev_t, c + a)
        elif c > prev_t:
            trail[i] = c - a
        else:
            trail[i] = c + a

    return pd.Series(trail, index=df.index)


class UTBotStrategy(BaseStrategy):

    def __init__(self):
        self.atr_period = settings.UT_ATR_PERIOD
        self.key_value  = settings.UT_KEY_VALUE
        self.ema_filter = settings.UT_EMA_FILTER
        self.risk       = settings.RISK_PER_TRADE_PCT
        log.info(f"UT Bot | ATR={self.atr_period} KeyValue={self.key_value} "
                 f"EMA={self.ema_filter}")

    @property
    def min_candles_required(self) -> int:
        return max(self.ema_filter, self.atr_period) + 5

    def generate_signal(self, df: pd.DataFrame, mid_price: float,
                        current_position: float, collateral: float) -> Signal:

        close   = df["close"]
        trail   = compute_ut_trail(df, self.atr_period, self.key_value)
        ema200  = ema(close, self.ema_filter)
        atr_val = current_atr(df, self.atr_period)

        prev_close = float(close.iloc[-2])
        curr_close = float(close.iloc[-1])
        prev_trail = float(trail.iloc[-2])
        curr_trail = float(trail.iloc[-1])
        ema_val    = float(ema200.iloc[-1])

        crossed_above = prev_close <= prev_trail and curr_close > curr_trail
        crossed_below = prev_close >= prev_trail and curr_close < curr_trail
        above_ema     = curr_close > ema_val
        below_ema     = curr_close < ema_val

        log.debug(
            f"UT Bot | close={curr_close:.5f} trail={curr_trail:.5f} "
            f"ema200={ema_val:.5f} ↑={crossed_above} ↓={crossed_below}"
        )

        # ── Exit ──────────────────────────────────────────────────────────────
        if current_position > 0 and crossed_below:
            return Signal(
                direction=Direction.FLAT,
                entry_price=mid_price, stop_loss=0.0, take_profit=0.0,
                size_xrp=abs(current_position),
                reason=f"Exit LONG | price crossed below trail={curr_trail:.5f}",
            )
        if current_position < 0 and crossed_above:
            return Signal(
                direction=Direction.FLAT,
                entry_price=mid_price, stop_loss=0.0, take_profit=0.0,
                size_xrp=abs(current_position),
                reason=f"Exit SHORT | price crossed above trail={curr_trail:.5f}",
            )

        # ── Entry ─────────────────────────────────────────────────────────────
        if current_position == 0:
            size = self._size(collateral, atr_val)

            if crossed_above and above_ema:
                stop = curr_trail
                tp   = mid_price + (mid_price - stop) * settings.ATR_TP_MULTIPLIER
                return Signal(
                    direction=Direction.LONG,
                    entry_price=mid_price, stop_loss=stop, take_profit=tp,
                    size_xrp=size,
                    reason=f"LONG | trail={curr_trail:.5f} ema={ema_val:.5f}",
                )

            if crossed_below and below_ema:
                stop = curr_trail
                tp   = mid_price - (stop - mid_price) * settings.ATR_TP_MULTIPLIER
                return Signal(
                    direction=Direction.SHORT,
                    entry_price=mid_price, stop_loss=stop, take_profit=tp,
                    size_xrp=size,
                    reason=f"SHORT | trail={curr_trail:.5f} ema={ema_val:.5f}",
                )

        return Signal(
            direction=Direction.FLAT,
            entry_price=mid_price, stop_loss=0.0, take_profit=0.0,
            size_xrp=0.0,
            reason=f"No signal | trail={curr_trail:.5f}",
        )

    def _size(self, collateral: float, atr: float) -> float:
        risk_usdc   = collateral * self.risk
        sl_distance = atr * self.key_value
        if sl_distance == 0:
            return 0.0
        return min(risk_usdc / sl_distance, settings.MAX_ORDER_SIZE_XRP)
