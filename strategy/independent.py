"""
strategy/independent.py
-----------------------
Independent Multi-Strategy Runner

Each strategy runs completely independently:
  - TrendFollowing  manages its own position
  - MeanReversion   manages its own position  
  - UTBot           manages its own position

Each gets its own slice of collateral (collateral / num_strategies).
Each tracks its own entry, SL, TP independently.
No cross-strategy dependency — one firing doesn't block another.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from strategy.base import BaseStrategy, Direction, Signal
from strategy.trend_following import TrendFollowingStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.ut_bot import UTBotStrategy
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class StrategySlot:
    """Tracks one strategy's independent state."""
    name: str
    strategy: BaseStrategy
    position: float = 0.0        # current XRP position for this slot
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0


class IndependentMultiStrategy:
    """
    Runs TF, MR, and UT Bot independently.
    Each has its own position slice and generates signals independently.
    Returns a list of (slot_name, Signal) tuples every tick.
    """

    def __init__(self):
        self.slots = [
            StrategySlot("TrendFollowing", TrendFollowingStrategy()),
            StrategySlot("MeanReversion",  MeanReversionStrategy()),
            StrategySlot("UTBot",          UTBotStrategy()),
        ]
        log.info("Independent mode: TrendFollowing + MeanReversion + UTBot running separately")

    @property
    def min_candles_required(self) -> int:
        return max(s.strategy.min_candles_required for s in self.slots)

    def get_signals(
        self,
        df: pd.DataFrame,
        mid_price: float,
        total_collateral: float,
    ) -> list[tuple[str, Signal]]:
        """
        Generate independent signals for each strategy.
        Each strategy gets 1/3 of total collateral for sizing.
        Returns list of (strategy_name, Signal).
        """
        collateral_slice = total_collateral / len(self.slots)
        results = []

        for slot in self.slots:
            sig = slot.strategy.generate_signal(
                df=df,
                mid_price=mid_price,
                current_position=slot.position,
                collateral=collateral_slice,
            )

            # Update slot tracking on entry/exit
            if sig.direction != Direction.FLAT and slot.position == 0:
                # New entry
                slot.entry_price = sig.entry_price
                slot.stop_loss   = sig.stop_loss
                slot.take_profit = sig.take_profit
                slot.position    = sig.size_xrp if sig.direction == Direction.LONG else -sig.size_xrp
            elif sig.direction == Direction.FLAT and slot.position != 0:
                # Exit
                slot.position    = 0.0
                slot.entry_price = 0.0
                slot.stop_loss   = 0.0
                slot.take_profit = 0.0

            results.append((slot.name, sig))

            log.debug(
                f"[{slot.name}] {sig.direction.name} | "
                f"pos={slot.position:.1f} | {sig.reason[:60]}"
            )

        return results

    def check_sl_tp(self, mid_price: float) -> list[tuple[str, str]]:
        """
        Check SL/TP for each slot's open position.
        Returns list of (strategy_name, "stop_loss"|"take_profit") for hits.
        """
        hits = []
        for slot in self.slots:
            if slot.position == 0:
                continue

            if slot.position > 0:  # Long
                if slot.stop_loss > 0 and mid_price <= slot.stop_loss:
                    hits.append((slot.name, "stop_loss"))
                    slot.position = 0.0
                elif slot.take_profit > 0 and mid_price >= slot.take_profit:
                    hits.append((slot.name, "take_profit"))
                    slot.position = 0.0

            elif slot.position < 0:  # Short
                if slot.stop_loss > 0 and mid_price >= slot.stop_loss:
                    hits.append((slot.name, "stop_loss"))
                    slot.position = 0.0
                elif slot.take_profit > 0 and mid_price <= slot.take_profit:
                    hits.append((slot.name, "take_profit"))
                    slot.position = 0.0

        return hits

    def get_status(self) -> str:
        """One-line status of all slots for logging."""
        parts = []
        for slot in self.slots:
            if slot.position == 0:
                parts.append(f"{slot.name}=FLAT")
            else:
                direction = "LONG" if slot.position > 0 else "SHORT"
                parts.append(f"{slot.name}={direction}({slot.position:.1f}XRP)")
        return " | ".join(parts)
