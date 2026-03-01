"""
execution/order_manager.py
--------------------------
All order operations go through here.  Handles:

  • Unique client_order_index generation (monotonically increasing, global)
  • Placing limit / market orders
  • Cancelling open orders
  • Stop-loss & take-profit monitoring (polled, since Lighter uses limit orders)
  • Tracking open order state

Lighter facts baked in:
  - client_order_index must be unique ACROSS ALL MARKETS per account
  - base_amount and price are INTEGERS scaled by base_size / base_price
  - cancel uses the same client_order_index as the original create
"""
from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass, field
from typing import Optional

import lighter

from core.client import get_signer, get_api_client, get_market_meta
from core.exceptions import OrderError
from config import settings
from strategy.base import Direction, Signal
from utils.math_utils import to_lighter_price, to_lighter_amount
from utils.logger import get_logger

log = get_logger(__name__)


# ── Order tracking ─────────────────────────────────────────────────────────────

@dataclass
class TrackedOrder:
    client_order_index: int
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    size_xrp: float
    placed_at: float = field(default_factory=time.time)
    is_open: bool = True


_open_orders: dict[int, TrackedOrder] = {}   # client_order_index → TrackedOrder
_order_counter: int = int(time.time() * 1000) % 10_000_000   # start from a stable base


def _next_order_index() -> int:
    global _order_counter
    _order_counter += 1
    return _order_counter


# ── Order placement ────────────────────────────────────────────────────────────

async def place_limit_order(
    direction: Direction,
    price: float,
    size_xrp: float,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    reason: str = "",
) -> int:
    """
    Place a limit order on the XRP market.
    Returns the client_order_index.
    """
    meta    = await get_market_meta()
    bp      = meta["base_price"]
    bs      = meta["base_size"]
    signer  = get_signer()

    idx          = _next_order_index()
    raw_price    = to_lighter_price(price, bp)
    raw_amount   = to_lighter_amount(size_xrp, bs)
    is_ask       = (direction == Direction.SHORT)

    log.info(f"{'SELL' if is_ask else 'BUY '} LIMIT | "
             f"idx={idx} price={price:.4f} size={size_xrp:.2f} XRP | {reason}")

    tx, tx_hash, err = await signer.create_order(
        market_index=settings.XRP_MARKET_INDEX,
        client_order_index=idx,
        base_amount=raw_amount,
        price=raw_price,
        is_ask=is_ask,
        order_type=signer.ORDER_TYPE_LIMIT,
        time_in_force=signer.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME,
        reduce_only=False,
        order_expiry=0,
    )

    if err:
        raise OrderError(f"Limit order failed (idx={idx}): {err}")

    log.success(f"Order placed | hash={tx_hash} idx={idx}")

    _open_orders[idx] = TrackedOrder(
        client_order_index=idx,
        direction=direction,
        entry_price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        size_xrp=size_xrp,
    )
    return idx


async def place_market_order(
    direction: Direction,
    size_xrp: float,
    worst_price: float,
    reason: str = "",
) -> int:
    """
    Place a market (IOC) order.  `worst_price` is the price limit —
    the order fills at market but won't execute worse than this.
    """
    meta    = await get_market_meta()
    bp      = meta["base_price"]
    bs      = meta["base_size"]
    signer  = get_signer()

    idx        = _next_order_index()
    raw_price  = to_lighter_price(worst_price, bp)
    raw_amount = to_lighter_amount(size_xrp, bs)
    is_ask     = (direction == Direction.SHORT)

    log.info(f"{'SELL' if is_ask else 'BUY '} MARKET | "
             f"idx={idx} worst_px={worst_price:.4f} size={size_xrp:.2f} XRP | {reason}")

    tx, tx_hash, err = await signer.create_order(
        market_index=settings.XRP_MARKET_INDEX,
        client_order_index=idx,
        base_amount=raw_amount,
        price=raw_price,
        is_ask=is_ask,
        order_type=signer.ORDER_TYPE_MARKET,
        time_in_force=signer.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL,
        reduce_only=False,
        order_expiry=signer.DEFAULT_IOC_EXPIRY,
    )

    if err:
        raise OrderError(f"Market order failed (idx={idx}): {err}")

    log.success(f"Market order placed | hash={tx_hash} idx={idx}")

    # Market orders typically fill immediately, so mark as closed
    _open_orders[idx] = TrackedOrder(
        client_order_index=idx,
        direction=direction,
        entry_price=worst_price,
        stop_loss=0.0,
        take_profit=0.0,
        size_xrp=size_xrp,
        is_open=False,
    )
    return idx


async def cancel_order(client_order_index: int) -> None:
    """Cancel an open order by its client_order_index."""
    signer = get_signer()

    log.info(f"Cancelling order idx={client_order_index}")
    tx, tx_hash, err = await signer.create_cancel_order(
        market_index=settings.XRP_MARKET_INDEX,
        order_index=client_order_index,
    )
    if err:
        raise OrderError(f"Cancel failed (idx={client_order_index}): {err}")

    log.success(f"Cancelled | hash={tx_hash} idx={client_order_index}")
    if client_order_index in _open_orders:
        _open_orders[client_order_index].is_open = False


async def cancel_all() -> None:
    """Cancel ALL open orders on the XRP market (ScheduledCancelAll)."""
    signer = get_signer()
    tx, tx_hash, err = await signer.cancel_all_orders(
        market_index=settings.XRP_MARKET_INDEX,
        time_in_force=signer.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME,
    )
    if err:
        raise OrderError(f"cancel_all failed: {err}")
    for o in _open_orders.values():
        o.is_open = False
    log.warning(f"All orders cancelled | hash={tx_hash}")


# ── Stop-loss / Take-profit monitor ───────────────────────────────────────────

async def check_sl_tp(mid_price: float, current_position: float) -> Optional[str]:
    """
    Poll open orders for SL/TP breach.
    Returns "stop_loss", "take_profit", or None.

    In production you'd replace this with WebSocket fill events.
    """
    for idx, order in list(_open_orders.items()):
        if not order.is_open:
            continue

        hit = None

        if order.direction == Direction.LONG:
            if order.stop_loss > 0 and mid_price <= order.stop_loss:
                hit = "stop_loss"
            elif order.take_profit > 0 and mid_price >= order.take_profit:
                hit = "take_profit"

        elif order.direction == Direction.SHORT:
            if order.stop_loss > 0 and mid_price >= order.stop_loss:
                hit = "stop_loss"
            elif order.take_profit > 0 and mid_price <= order.take_profit:
                hit = "take_profit"

        if hit:
            log.warning(f"SL/TP {hit.upper()} hit | mid={mid_price:.4f} "
                        f"SL={order.stop_loss:.4f} TP={order.take_profit:.4f}")
            return hit

    return None


def get_open_orders() -> dict[int, TrackedOrder]:
    return {k: v for k, v in _open_orders.items() if v.is_open}
