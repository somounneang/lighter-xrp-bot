"""
strategy/mean_reversion.py
--------------------------
Bollinger Band Mean-Reversion Strategy

Logic
-----
BUY  : Price bounces off lower Bollinger Band  AND  RSI < 40
SELL : Price rejects from upper Bollinger Band AND  RSI > 60
Exit : Price reaches the mid-band (mean reversion complete)

Avoids flat/squeezed markets (band width too narrow).
"""
from __future__ import annotations

import pandas as pd

from config import settings
from strategy.base import BaseStrategy, Direction, Signal
from strategy.indicators import bb_signal, bollinger_bands, current_rsi, current_atr
from utils.logger import get_logger

log = get_logger(__name__)

RSI_ENTRY_LONG  = 40   # RSI must be below this to enter long
RSI_ENTRY_SHORT = 60   # RSI must be above this to enter short


class MeanReversionStrategy(BaseStrategy):

    def __init__(self):
        self.period  = settings.BB_PERIOD
        self.std     = settings.BB_STD_DEV
        self.squeeze = settings.BB_MIN_SQUEEZE
        self.risk    = settings.RISK_PER_TRADE_PCT
        self.atr_p   = settings.ATR_PERIOD

    @property
    def min_candles_required(self) -> int:
        return self.period + 5

    def generate_signal(self, df: pd.DataFrame, mid_price: float,
                        current_position: float, collateral: float) -> Signal:

        bb       = bollinger_bands(df, self.period, self.std)
        bb_sig   = bb_signal(df, self.period, self.std, self.squeeze)
        rsi_val  = current_rsi(df, 14)
        atr_val  = current_atr(df, self.atr_p)
        bb_mid   = float(bb["mid"].iloc[-1])

        log.debug(f"MR indicators | bb_sig={bb_sig} RSI={rsi_val:.1f} "
                  f"BB_mid={bb_mid:.4f}")

        # ── Exit: price returned to the mean ─────────────────────────────────
        if current_position > 0 and mid_price >= bb_mid:
            return Signal(
                direction=Direction.FLAT,
                entry_price=mid_price,
                stop_loss=0.0,
                take_profit=0.0,
                size_xrp=abs(current_position),
                reason=f"Exit LONG (mean reached @ {bb_mid:.4f})",
            )

        if current_position < 0 and mid_price <= bb_mid:
            return Signal(
                direction=Direction.FLAT,
                entry_price=mid_price,
                stop_loss=0.0,
                take_profit=0.0,
                size_xrp=abs(current_position),
                reason=f"Exit SHORT (mean reached @ {bb_mid:.4f})",
            )

        # ── Entry ─────────────────────────────────────────────────────────────
        if current_position == 0:
            size = self._size(collateral, atr_val)

            if bb_sig == 1 and rsi_val < RSI_ENTRY_LONG:
                lower = float(bb["lower"].iloc[-1])
                stop  = lower - atr_val
                tp    = bb_mid
                return Signal(
                    direction=Direction.LONG,
                    entry_price=mid_price,
                    stop_loss=stop,
                    take_profit=tp,
                    size_xrp=size,
                    reason=f"MR LONG bounce off lower BB | RSI={rsi_val:.1f}",
                )

            if bb_sig == -1 and rsi_val > RSI_ENTRY_SHORT:
                upper = float(bb["upper"].iloc[-1])
                stop  = upper + atr_val
                tp    = bb_mid
                return Signal(
                    direction=Direction.SHORT,
                    entry_price=mid_price,
                    stop_loss=stop,
                    take_profit=tp,
                    size_xrp=size,
                    reason=f"MR SHORT rejection from upper BB | RSI={rsi_val:.1f}",
                )

        return Signal(
            direction=Direction.FLAT,
            entry_price=mid_price,
            stop_loss=0.0,
            take_profit=0.0,
            size_xrp=0.0,
            reason="No signal",
        )

    def _size(self, collateral: float, atr: float) -> float:
        risk_usdc   = collateral * self.risk
        sl_distance = atr
        if sl_distance == 0:
            return 0.0
        return min(risk_usdc / sl_distance, settings.MAX_ORDER_SIZE_XRP)
