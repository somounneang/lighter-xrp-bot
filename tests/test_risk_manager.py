"""tests/test_risk_manager.py"""
import pytest
from strategy.base import Signal, Direction
from execution import risk_manager as rm
from core.exceptions import KillSwitchError, RiskLimitError
from config import settings


def _sig(direction=Direction.LONG, size=10.0, sl=1.9, tp=2.3, entry=2.0):
    return Signal(direction=direction, entry_price=entry,
                  stop_loss=sl, take_profit=tp, size_xrp=size)


def setup_function():
    """Reset risk state before each test."""
    rm._state = rm.RiskState()


def test_valid_long_passes():
    sig = rm.validate_signal(_sig(), current_position=0.0)
    assert sig.direction == Direction.LONG


def test_size_clipped():
    original_max = settings.MAX_ORDER_SIZE_XRP
    sig = rm.validate_signal(_sig(size=original_max * 2), current_position=0.0)
    assert sig.size_xrp == original_max


def test_position_limit_rejected():
    sig = _sig(size=settings.MAX_POSITION_SIZE + 1)
    with pytest.raises(RiskLimitError):
        rm.validate_signal(sig, current_position=0.0)


def test_bad_stop_loss_long():
    sig = _sig(direction=Direction.LONG, sl=2.5, entry=2.0)  # SL above entry
    with pytest.raises(RiskLimitError):
        rm.validate_signal(sig, current_position=0.0)


def test_kill_switch_triggers():
    rm._state.daily_realized_pnl = 0.0
    with pytest.raises(KillSwitchError):
        rm.record_pnl(-(settings.MAX_DAILY_LOSS_USDC + 1))


def test_flat_always_passes():
    sig = Signal(Direction.FLAT, 2.0, 0.0, 0.0, 5.0)
    result = rm.validate_signal(sig, current_position=10.0)
    assert result.direction == Direction.FLAT
