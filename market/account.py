"""
market/account.py
-----------------
Fetches live account state: collateral, XRP position, P&L.

Confirmed SDK method: lighter.AccountApi(client).account(by="index", value="N")
"""
from __future__ import annotations

import lighter
from core.client import get_api_client
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


async def get_account_state() -> dict:
    """
    Returns:
        {
          "collateral":       float,
          "position":         float,  # signed (+long, -short)
          "avg_entry_price":  float,
          "unrealized_pnl":   float,
          "realized_pnl":     float,
        }
    """
    client = get_api_client()
    api = lighter.AccountApi(client)
    acct = await api.account(by="index", value=str(settings.ACCOUNT_INDEX))

    collateral = float(getattr(acct, "collateral", 0) or 0)
    position   = 0.0
    avg_entry  = 0.0
    unrealized = 0.0
    realized   = 0.0

    for pos in (getattr(acct, "positions", None) or []):
        if int(getattr(pos, "market_id", -1)) == settings.XRP_MARKET_INDEX:
            sign       = int(getattr(pos, "sign", 1))
            position   = float(getattr(pos, "position", 0)) * sign
            avg_entry  = float(getattr(pos, "avg_entry_price", 0))
            unrealized = float(getattr(pos, "unrealized_pnl", 0))
            realized   = float(getattr(pos, "realized_pnl", 0))
            break

    return {
        "collateral":      collateral,
        "position":        position,
        "avg_entry_price": avg_entry,
        "unrealized_pnl":  unrealized,
        "realized_pnl":    realized,
    }
