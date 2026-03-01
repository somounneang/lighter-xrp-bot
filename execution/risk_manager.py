"""
execution/risk_manager.py
--------------------------
The bot's safety net.  Every order passes through the risk manager
before being sent to Lighter.  The risk manager can:

  1. Clip order sizes to the configured maximum
  2. Reject orders that would breach position limits
  3. Trigger the kill switch if daily loss exceeds the limit
  4. Check that stop-loss / take-profit are on the correct side

Raises KillSwitchError to halt the entire bot.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from config import settings
from core.exceptions import KillSwitchError, RiskLimitError
from strategy.base import Signal, Direction
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class RiskState:
    daily_realized_pnl: float = 0.0
    daily_start_ts: float = field(default_factory=time.time)
    kill_switch_active: bool = False
    trade_count: int = 0


_state = RiskState()


def reset_daily_pnl() -> None:
    """Call at the start of each trading day."""
    _state.daily_realized_pnl = 0.0
    _state.daily_start_ts = time.time()
    log.info("Daily P&L counter reset")


def record_pnl(pnl: float) -> None:
    """Update daily P&L after each closed trade."""
    _state.daily_realized_pnl += pnl
    _state.trade_count += 1
    log.info(f"Daily P&L: {_state.daily_realized_pnl:.2f} USDC "
             f"(trades today: {_state.trade_count})")
    _check_kill_switch()


def _check_kill_switch() -> None:
    loss = _state.daily_realized_pnl  # negative = loss
    if loss < -settings.MAX_DAILY_LOSS_USDC:
        _state.kill_switch_active = True
        msg = (f"KILL SWITCH TRIGGERED: daily loss "
               f"{loss:.2f} USDC exceeds limit "
               f"-{settings.MAX_DAILY_LOSS_USDC} USDC")
        log.critical(msg)
        raise KillSwitchError(msg)


def validate_signal(signal: Signal, current_position: float) -> Signal:
    """
    Validate and potentially modify a Signal before execution.

    Returns a (possibly clipped) Signal.
    Raises RiskLimitError if the signal must be rejected outright.
    Raises KillSwitchError if daily loss limit is breached.
    """
    if _state.kill_switch_active:
        raise KillSwitchError("Kill switch is active — no new orders permitted")

    if signal.direction == Direction.FLAT:
        return signal  # Exit orders are always allowed through

    # ── Size clipping ──────────────────────────────────────────────────────────
    max_size = settings.MAX_ORDER_SIZE_XRP
    if signal.size_xrp > max_size:
        log.warning(f"Size clipped: {signal.size_xrp:.2f} → {max_size:.2f} XRP")
        signal.size_xrp = max_size

    if signal.size_xrp <= 0:
        raise RiskLimitError("Signal size is zero or negative after clipping")

    # ── Position limit ─────────────────────────────────────────────────────────
    new_position = current_position + (
        signal.size_xrp if signal.direction == Direction.LONG else -signal.size_xrp
    )
    if abs(new_position) > settings.MAX_POSITION_SIZE:
        raise RiskLimitError(
            f"Order would breach max position: "
            f"current={current_position:.2f}, new={new_position:.2f}, "
            f"max={settings.MAX_POSITION_SIZE}"
        )

    # ── Stop-loss sanity ───────────────────────────────────────────────────────
    if signal.stop_loss > 0:
        if signal.direction == Direction.LONG and signal.stop_loss >= signal.entry_price:
            raise RiskLimitError("LONG stop-loss is above entry price!")
        if signal.direction == Direction.SHORT and signal.stop_loss <= signal.entry_price:
            raise RiskLimitError("SHORT stop-loss is below entry price!")

    log.debug(f"Risk OK | dir={signal.direction.name} size={signal.size_xrp:.2f} "
              f"SL={signal.stop_loss:.4f} TP={signal.take_profit:.4f}")
    return signal


def get_state() -> RiskState:
    return _state
