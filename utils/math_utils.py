"""
utils/math_utils.py
-------------------
Helpers for converting human-readable prices/sizes into the integer
values that Lighter requires, and back.

Lighter uses integer prices/amounts scaled by the market's tick/lot size.
Query `orderbook_details` to get `base_size` (lot) and `base_price` (tick)
for each market.
"""
import math


def to_lighter_price(human_price: float, base_price: int) -> int:
    """
    Convert a human-readable price (e.g. 2.35) to Lighter integer price.

    `base_price` is the price tick unit from orderbook_details.
    e.g. if base_price=100 the integer 235 represents $2.35.
    """
    return int(round(human_price * base_price))


def from_lighter_price(raw_price: int, base_price: int) -> float:
    """Convert Lighter integer price back to float."""
    return raw_price / base_price


def to_lighter_amount(human_amount: float, base_size: int) -> int:
    """
    Convert a human-readable base amount (e.g. 10.5 XRP) to Lighter integer.

    `base_size` is the lot size unit from orderbook_details.
    """
    return int(round(human_amount * base_size))


def from_lighter_amount(raw_amount: int, base_size: int) -> float:
    """Convert Lighter integer amount back to float."""
    return raw_amount / base_size


def round_to_tick(price: float, tick: float) -> float:
    """Round a price down to the nearest tick boundary."""
    return math.floor(price / tick) * tick


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
