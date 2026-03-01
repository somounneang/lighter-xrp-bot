"""
market/orderbook.py
-------------------
Fetches and parses the XRP-USD orderbook from Lighter.
Returns clean Python dicts — no SDK types leak beyond this module.
"""
from __future__ import annotations

import lighter
from core.client import get_api_client, get_market_meta
from core.exceptions import MarketDataError
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


async def fetch_orderbook(depth: int = 20) -> dict:
    """
    Fetch the current orderbook.

    Returns:
        {
          "bids": [{"price": float, "size": float}, ...],   # best bid first
          "asks": [{"price": float, "size": float}, ...],   # best ask first
          "mid":  float,
          "spread": float,
        }
    """
    try:
        client = get_api_client()
        meta = await get_market_meta()
        bp = meta["base_price"]
        bs = meta["base_size"]

        market_api = lighter.MarketApi(client)
        raw = await market_api.orderbook(
            market_index=settings.XRP_MARKET_INDEX,
            depth=depth,
        )

        def _parse_levels(levels):
            result = []
            for lvl in (levels or []):
                result.append({
                    "price": int(lvl.price) / bp,
                    "size":  int(lvl.amount) / bs,
                })
            return result

        bids = _parse_levels(raw.bids)
        asks = _parse_levels(raw.asks)

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
