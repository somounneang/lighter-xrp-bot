"""
market/orderbook.py
-------------------
Confirmed real API response structure:
  raw = await order_api.order_book_orders(market_id=7, limit=N)
  raw.bids  → list of SimpleOrder  (highest price first)
  raw.asks  → list of SimpleOrder  (lowest price first)
  Each SimpleOrder: .price (str), .remaining_base_amount (str)
"""
from __future__ import annotations

import lighter
from core.client import get_api_client
from core.exceptions import MarketDataError
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


async def fetch_orderbook(depth: int = 20) -> dict:
    try:
        client = get_api_client()
        order_api = lighter.OrderApi(client)
        raw = await order_api.order_book_orders(
            market_id=settings.XRP_MARKET_INDEX,
            limit=depth,
        )

        def _parse(levels):
            return [
                {
                    "price": float(lvl.price),
                    "size":  float(lvl.remaining_base_amount),
                }
                for lvl in (levels or [])
            ]

        bids = _parse(getattr(raw, "bids", []))
        asks = _parse(getattr(raw, "asks", []))

        if not bids or not asks:
            raise MarketDataError("Orderbook returned empty bids or asks")

        mid    = (bids[0]["price"] + asks[0]["price"]) / 2
        spread = asks[0]["price"] - bids[0]["price"]

        log.debug(f"OB | best_bid={bids[0]['price']} best_ask={asks[0]['price']} mid={mid:.6f}")
        return {"bids": bids, "asks": asks, "mid": mid, "spread": spread}

    except MarketDataError:
        raise
    except Exception as exc:
        raise MarketDataError(f"Failed to fetch orderbook: {exc}") from exc


async def get_mid_price() -> float:
    return (await fetch_orderbook(depth=5))["mid"]