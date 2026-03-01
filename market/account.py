"""
market/account.py
-----------------
Fetches live account state: collateral balance, open XRP position,
and unrealised P&L.
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
          "collateral":       float,   # USDC free collateral
          "position":         float,   # signed XRP position (+long, -short)
          "avg_entry_price":  float,
          "unrealized_pnl":   float,
          "realized_pnl":     float,
        }
    """
    client = get_api_client()
    api = lighter.AccountApi(client)
    acct = await api.account_by_index(account_index=settings.ACCOUNT_INDEX)

    collateral = float(acct.collateral or 0)

    # Find XRP position if it exists
    position      = 0.0
    avg_entry     = 0.0
    unrealized    = 0.0
    realized      = 0.0

    if acct.positions:
        for pos in acct.positions:
            if int(pos.market_id) == settings.XRP_MARKET_INDEX:
                sign         = int(pos.sign)         # 1=long, -1=short
                position     = float(pos.position) * sign
                avg_entry    = float(pos.avg_entry_price)
                unrealized   = float(pos.unrealized_pnl)
                realized     = float(pos.realized_pnl)
                break

    return {
        "collateral":      collateral,
        "position":        position,
        "avg_entry_price": avg_entry,
        "unrealized_pnl":  unrealized,
        "realized_pnl":    realized,
    }
