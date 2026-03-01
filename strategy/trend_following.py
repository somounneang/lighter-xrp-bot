"""
strategy/trend_following.py
----------------------------
EMA Crossover + RSI Confirmation + ATR-based Stop-Loss & Take-Profit

Logic
-----
LONG entry  : Fast EMA crosses above Slow EMA  AND  RSI < RSI_OVERBOUGHT
SHORT entry : Fast EMA crosses below Slow EMA  AND  RSI > RSI_OVERSOLD
Exit        : Opposite crossover OR RSI extreme / stop-loss / take-profit hit

Stop-loss   = entry_price  ± ATR * ATR_SL_MULTIPLIER
Take-profit = entry_price  ± ATR * ATR_TP_MULTIPLIER

Position sizing: risk 1% of collateral per trade.
    size = (collateral * risk_pct) / (ATR * SL_mult)
"""
from __future__ import annotations

import pandas as pd

from config import settings
from strategy.base import BaseStrategy, Direction, Signal
from strategy.indicators import (
    ema_crossover_signal, trend_direction,
    current_rsi, current_atr,
)
from utils.logger import get_logger

log = get_logger(__name__)


class TrendFollowingStrategy(BaseStrategy):

    def __init__(self):
        self.fast  = settings.EMA_FAST
        self.slow  = settings.EMA_SLOW
        self.rsi_p = settings.RSI_PERIOD
        self.rsi_ob = settings.RSI_OVERBOUGHT
        self.rsi_os = settings.RSI_OVERSOLD
        self.atr_p  = settings.ATR_PERIOD
        self.sl_mul = settings.ATR_SL_MULTIPLIER
        self.tp_mul = settings.ATR_TP_MULTIPLIER
        self.risk   = settings.RISK_PER_TRADE_PCT

    @property
    def min_candles_required(self) -> int:
        return max(self.slow, self.rsi_p, self.atr_p) + 5

    def generate_signal(self, df: pd.DataFrame, mid_price: float,
                        current_position: float, collateral: float) -> Signal:

        crossover = ema_crossover_signal(df, self.fast, self.slow)
        trend     = trend_direction(df, self.fast, self.slow)
        rsi_val   = current_rsi(df, self.rsi_p)
        atr_val   = current_atr(df, self.atr_p)

        log.debug(f"TF indicators | crossover={crossover} trend={trend} "
                  f"RSI={rsi_val:.1f} ATR={atr_val:.4f}")

        # ── Exit signals (override entry) ─────────────────────────────────────
        if current_position > 0 and (crossover == -1 or rsi_val > self.rsi_ob):
            return Signal(
                direction=Direction.FLAT,
                entry_price=mid_price,
                stop_loss=0.0,
                take_profit=0.0,
                size_xrp=abs(current_position),
                reason=f"Exit LONG | crossover={crossover} RSI={rsi_val:.1f}",
            )

        if current_position < 0 and (crossover == 1 or rsi_val < self.rsi_os):
            return Signal(
                direction=Direction.FLAT,
                entry_price=mid_price,
                stop_loss=0.0,
                take_profit=0.0,
                size_xrp=abs(current_position),
                reason=f"Exit SHORT | crossover={crossover} RSI={rsi_val:.1f}",
            )

        # ── Entry signals ─────────────────────────────────────────────────────
        # Only enter when there's a fresh crossover and no existing position
        if current_position == 0:

            if crossover == 1 and rsi_val < self.rsi_ob:
                # LONG
                stop  = mid_price - atr_val * self.sl_mul
                tp    = mid_price + atr_val * self.tp_mul
                size  = self._size(collateral, atr_val)
                return Signal(
                    direction=Direction.LONG,
                    entry_price=mid_price,
                    stop_loss=stop,
                    take_profit=tp,
                    size_xrp=size,
                    reason=f"LONG entry | RSI={rsi_val:.1f} ATR={atr_val:.4f}",
                )

            if crossover == -1 and rsi_val > self.rsi_os:
                # SHORT
                stop  = mid_price + atr_val * self.sl_mul
                tp    = mid_price - atr_val * self.tp_mul
                size  = self._size(collateral, atr_val)
                return Signal(
                    direction=Direction.SHORT,
                    entry_price=mid_price,
                    stop_loss=stop,
                    take_profit=tp,
                    size_xrp=size,
                    reason=f"SHORT entry | RSI={rsi_val:.1f} ATR={atr_val:.4f}",
                )

        # No signal
        return Signal(
            direction=Direction.FLAT,
            entry_price=mid_price,
            stop_loss=0.0,
            take_profit=0.0,
            size_xrp=0.0,
            reason="No signal",
        )

    def _size(self, collateral: float, atr: float) -> float:
        """Risk-based position sizing."""
        risk_usdc = collateral * self.risk
        sl_distance = atr * self.sl_mul
        if sl_distance == 0:
            return 0.0
        size = risk_usdc / sl_distance
        return min(size, settings.MAX_ORDER_SIZE_XRP)
