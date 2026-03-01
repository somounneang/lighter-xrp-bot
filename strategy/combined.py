"""
strategy/combined.py
--------------------
Combined Strategy — requires BOTH trend-following AND mean-reversion
to agree before entering.  This dramatically reduces false signals.

Agreement rule:
    - TF says LONG  AND  MR says LONG  → Enter LONG  (strong confluence)
    - TF says SHORT AND  MR says SHORT → Enter SHORT (strong confluence)
    - Either says FLAT or they disagree → FLAT (sit out)
    - Either says EXIT → immediately exit

Size is the average of both strategy suggestions (already risk-capped).
"""
from __future__ import annotations

import pandas as pd

from strategy.base import BaseStrategy, Direction, Signal
from strategy.trend_following import TrendFollowingStrategy
from strategy.mean_reversion import MeanReversionStrategy
from utils.logger import get_logger

log = get_logger(__name__)


class CombinedStrategy(BaseStrategy):

    def __init__(self):
        self.tf = TrendFollowingStrategy()
        self.mr = MeanReversionStrategy()

    @property
    def min_candles_required(self) -> int:
        return max(self.tf.min_candles_required, self.mr.min_candles_required)

    def generate_signal(self, df: pd.DataFrame, mid_price: float,
                        current_position: float, collateral: float) -> Signal:

        tf_sig = self.tf.generate_signal(df, mid_price, current_position, collateral)
        mr_sig = self.mr.generate_signal(df, mid_price, current_position, collateral)

        log.debug(f"TF={tf_sig.direction.name}({tf_sig.reason}) | "
                  f"MR={mr_sig.direction.name}({mr_sig.reason})")

        # Exit takes priority — if either strategy says exit, we exit
        if (tf_sig.direction == Direction.FLAT and current_position != 0 and "Exit" in tf_sig.reason):
            tf_sig.reason = f"[Combined-TF exit] {tf_sig.reason}"
            return tf_sig

        if (mr_sig.direction == Direction.FLAT and current_position != 0 and "Exit" in mr_sig.reason):
            mr_sig.reason = f"[Combined-MR exit] {mr_sig.reason}"
            return mr_sig

        # Both agree on direction → enter
        if tf_sig.direction == mr_sig.direction and tf_sig.direction != Direction.FLAT:
            avg_size = (tf_sig.size_xrp + mr_sig.size_xrp) / 2
            # Use TF's stop/tp (ATR-based, generally tighter)
            return Signal(
                direction=tf_sig.direction,
                entry_price=tf_sig.entry_price,
                stop_loss=tf_sig.stop_loss,
                take_profit=tf_sig.take_profit,
                size_xrp=avg_size,
                reason=(f"[Combined CONFLUENCE] TF={tf_sig.reason} | MR={mr_sig.reason}"),
            )

        # No agreement → flat
        return Signal(
            direction=Direction.FLAT,
            entry_price=mid_price,
            stop_loss=0.0,
            take_profit=0.0,
            size_xrp=0.0,
            reason=f"No confluence | TF={tf_sig.reason} | MR={mr_sig.reason}",
        )
