"""
strategy/super_combined.py
--------------------------
Super Combined Strategy — ALL THREE must agree before entering.

  ✅ Trend Following  (EMA crossover + RSI)
  ✅ Mean Reversion   (Bollinger Band bounce + RSI)
  ✅ UT Bot Alert     (ATR trailing stop crossover + EMA-200 filter)

Entry rule : All 3 vote the SAME direction → enter
Exit rule  : ANY ONE signals exit → exit immediately (most conservative)

This produces the fewest signals but the highest quality — ideal for
a bot running 24/7 where you want to avoid overtrading XRP.
"""
from __future__ import annotations

import pandas as pd

from strategy.base import BaseStrategy, Direction, Signal
from strategy.trend_following import TrendFollowingStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.ut_bot import UTBotStrategy
from utils.logger import get_logger

log = get_logger(__name__)


class SuperCombinedStrategy(BaseStrategy):

    def __init__(self):
        self.tf = TrendFollowingStrategy()
        self.mr = MeanReversionStrategy()
        self.ut = UTBotStrategy()
        log.info("Super Combined: TrendFollowing + MeanReversion + UTBot")

    @property
    def min_candles_required(self) -> int:
        return max(
            self.tf.min_candles_required,
            self.mr.min_candles_required,
            self.ut.min_candles_required,
        )

    def generate_signal(self, df: pd.DataFrame, mid_price: float,
                        current_position: float, collateral: float) -> Signal:

        tf_sig = self.tf.generate_signal(df, mid_price, current_position, collateral)
        mr_sig = self.mr.generate_signal(df, mid_price, current_position, collateral)
        ut_sig = self.ut.generate_signal(df, mid_price, current_position, collateral)

        log.debug(
            f"SC votes | TF={tf_sig.direction.name} "
            f"MR={mr_sig.direction.name} "
            f"UT={ut_sig.direction.name}"
        )

        # ── Exit: ANY strategy says exit → close immediately ──────────────────
        if current_position != 0:
            for sig, name in [(tf_sig, "TF"), (mr_sig, "MR"), (ut_sig, "UT")]:
                if sig.direction == Direction.FLAT and "Exit" in sig.reason:
                    sig.reason = f"[SuperCombined {name} exit] {sig.reason}"
                    return sig

        # ── Entry: ALL THREE must agree ───────────────────────────────────────
        if current_position == 0:
            directions = {tf_sig.direction, mr_sig.direction, ut_sig.direction}

            if len(directions) == 1 and Direction.FLAT not in directions:
                agreed_dir = tf_sig.direction

                # Use UT Bot's stop (trail-based) — tightest and most dynamic
                # Average the sizes from all three
                avg_size = (tf_sig.size_xrp + mr_sig.size_xrp + ut_sig.size_xrp) / 3

                return Signal(
                    direction=agreed_dir,
                    entry_price=mid_price,
                    stop_loss=ut_sig.stop_loss,
                    take_profit=ut_sig.take_profit,
                    size_xrp=avg_size,
                    reason=(
                        f"[🔥 SUPER CONFLUENCE] "
                        f"TF={tf_sig.reason} | "
                        f"MR={mr_sig.reason} | "
                        f"UT={ut_sig.reason}"
                    ),
                )

        # ── Log vote breakdown when no confluence ─────────────────────────────
        votes = (
            f"TF={tf_sig.direction.name}({tf_sig.reason[:30]}) | "
            f"MR={mr_sig.direction.name}({mr_sig.reason[:30]}) | "
            f"UT={ut_sig.direction.name}({ut_sig.reason[:30]})"
        )

        return Signal(
            direction=Direction.FLAT,
            entry_price=mid_price,
            stop_loss=0.0, take_profit=0.0,
            size_xrp=0.0,
            reason=f"No confluence | {votes}",
        )
