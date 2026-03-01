"""
market/orderbook.py
-------------------
Fetches and parses the XRP orderbook from Lighter.

Confirmed from live API:
  lighter.OrderApi(client).order_book_orders(market_id=7)
  Response: raw.order_book_orders[0].ask_book / .bid_book
  Each level: .price (float), .amount (float) — no scaling needed
"""
from __future__ import annotations

import lighter
from core.client import get_api_client
from core.exceptions import MarketDataError
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


async def fetch_orderbook(depth: int = 20) -> dict:
    """
    Returns:
        {
          "bids": [{"price": float, "size": float}, ...],  # highest first
          "asks": [{"price": float, "size": float}, ...],  # lowest first
          "mid":  float,
          "spread": float,
        }
    """
    try:
        client = get_api_client()
        order_api = lighter.OrderApi(client)
        raw = await order_api.order_book_orders(market_id=settings.XRP_MARKET_INDEX)

        if hasattr(raw, "order_book_orders") and raw.order_book_orders:
            ob_data = raw.order_book_orders[0]
        else:
            ob_data = raw

        def _parse(levels):
            return [
                {"price": float(lvl.price), "size": float(lvl.amount)}
                for lvl in (levels or [])[:depth]
            ]

        asks = _parse(getattr(ob_data, "ask_book", []))
        bids = _parse(getattr(ob_data, "bid_book", []))

        if not bids or not asks:
            raise MarketDataError("Orderbook returned empty bids or asks")

        mid    = (bids[0]["price"] + asks[0]["price"]) / 2
        spread = asks[0]["price"] - bids[0]["price"]

        return {"bids": bids, "asks": asks, "mid": mid, "spread": spread}

    except MarketDataError:
        raise
    except Exception as exc:
        raise MarketDataError(f"Failed to fetch orderbook: {exc}") from exc


async def get_mid_price() -> float:
    ob = await fetch_orderbook(depth=1)
    return ob["mid"]
