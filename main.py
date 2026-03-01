"""
main.py
-------
XRP Trading Bot for Lighter.xyz

Strategies available (set STRATEGY in .env):
  trend_following   EMA crossover + RSI + ATR stops
  mean_reversion    Bollinger Band bounces + RSI filter
  combined          Both must agree (recommended — lower signal frequency, higher quality)

Run:
    python main.py                     # Start the bot
    python main.py --list-markets      # Print all markets and their indices (find XRP)
    python main.py --dry-run           # Simulate signals without placing real orders

Usage:
    1. Copy .env.example to .env and fill in your credentials
    2. Run --list-markets to confirm the XRP market_index
    3. Update XRP_MARKET_INDEX in .env
    4. Run --dry-run for a few cycles to verify signals look sane
    5. Remove --dry-run to go live
"""

from __future__ import annotations

import asyncio
import sys
import signal
import argparse
import time

import lighter

from config import settings
from core.client import get_signer, get_api_client, close_clients, get_market_meta
from core.exceptions import KillSwitchError, OrderError, RiskLimitError
from market.orderbook import fetch_orderbook, get_mid_price
from market.candles import get_candle_buffer
from market.account import get_account_state
from strategy.base import Direction, Signal
from strategy.trend_following import TrendFollowingStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.combined import CombinedStrategy
from execution.order_manager import (
    place_limit_order, place_market_order, cancel_all, check_sl_tp,
)
from execution import risk_manager as rm
from utils.logger import setup_logger, get_logger

log = get_logger(__name__)

# ── Graceful shutdown ──────────────────────────────────────────────────────────

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    log.warning(f"Received signal {sig} — initiating graceful shutdown...")
    _shutdown = True


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Strategy factory ───────────────────────────────────────────────────────────

def build_strategy():
    name = settings.STRATEGY.lower()
    if name == "trend_following":
        log.info("Strategy: Trend Following (EMA + RSI + ATR)")
        return TrendFollowingStrategy()
    elif name == "mean_reversion":
        log.info("Strategy: Mean Reversion (Bollinger Bands + RSI)")
        return MeanReversionStrategy()
    else:
        log.info("Strategy: Combined (Trend + Mean Reversion confluence)")
        return CombinedStrategy()


# ── Market listing helper ──────────────────────────────────────────────────────

async def list_markets():
    """Print all available markets with their indices — helps find XRP."""
    client = get_api_client()
    api = lighter.MarketApi(client)
    markets = await api.markets()
    print("\n{'─'*50}")
    print(f"{'Index':<8} {'Symbol':<15} {'Status'}")
    print("─" * 40)
    for m in markets.markets:
        print(f"{m.market_index:<8} {m.symbol:<15} {getattr(m, 'status', 'active')}")
    print("─" * 40)
    print("\nSet XRP_MARKET_INDEX in your .env to the index shown above.\n")
    await close_clients()


# ── Signal execution ───────────────────────────────────────────────────────────

async def execute_signal(sig: Signal, account: dict, dry_run: bool = False) -> None:
    """
    Translate a strategy Signal into actual orders (or log them in dry-run mode).
    """
    current_pos = account["position"]

    if sig.direction == Direction.FLAT and sig.size_xrp == 0:
        log.debug(f"No action | {sig.reason}")
        return

    # ── Close position ────────────────────────────────────────────────────────
    if sig.direction == Direction.FLAT and abs(current_pos) > 0:
        close_dir = Direction.SHORT if current_pos > 0 else Direction.LONG
        close_size = abs(current_pos)

        # Worst-price: 2% slippage tolerance
        slippage = 0.02
        worst_px = sig.entry_price * (1 - slippage) if close_dir == Direction.SHORT else \
                   sig.entry_price * (1 + slippage)

        log.info(f"[CLOSE] {close_dir.name} {close_size:.2f} XRP @ ~{sig.entry_price:.4f} | {sig.reason}")
        if not dry_run:
            await place_market_order(close_dir, close_size, worst_px, reason=sig.reason)
        else:
            log.info("[DRY-RUN] Would close position")
        return

    # ── Open position ─────────────────────────────────────────────────────────
    if sig.direction in (Direction.LONG, Direction.SHORT) and current_pos == 0:
        try:
            validated = rm.validate_signal(sig, current_pos)
        except RiskLimitError as e:
            log.warning(f"Risk rejected signal: {e}")
            return

        log.info(f"[ENTRY] {sig.direction.name} {validated.size_xrp:.2f} XRP "
                 f"@ {validated.entry_price:.4f} | SL={validated.stop_loss:.4f} "
                 f"TP={validated.take_profit:.4f} | {validated.reason}")

        if not dry_run:
            await place_limit_order(
                direction=validated.direction,
                price=validated.entry_price,
                size_xrp=validated.size_xrp,
                stop_loss=validated.stop_loss,
                take_profit=validated.take_profit,
                reason=validated.reason,
            )
        else:
            log.info("[DRY-RUN] Would place limit order")


# ── Main loop ──────────────────────────────────────────────────────────────────

async def run_bot(dry_run: bool = False) -> None:
    global _shutdown

    setup_logger(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)
    log.info("=" * 60)
    log.info("  XRP Trading Bot — Lighter.xyz")
    log.info(f"  Strategy : {settings.STRATEGY}")
    log.info(f"  Market   : XRP (index {settings.XRP_MARKET_INDEX})")
    log.info(f"  Dry-run  : {dry_run}")
    log.info("=" * 60)

    # Warm up clients
    _ = get_signer()
    _ = get_api_client()
    meta = await get_market_meta()
    log.info(f"Market metadata: {meta}")

    strategy    = build_strategy()
    candles     = get_candle_buffer(interval_seconds=60)
    warmup_done = False

    while not _shutdown:
        loop_start = time.time()

        try:
            # ── 1. Daily reset check ──────────────────────────────────────────
            state = rm.get_state()
            if time.time() - state.daily_start_ts > 86_400:
                rm.reset_daily_pnl()

            # ── 2. Fetch market data ──────────────────────────────────────────
            ob      = await fetch_orderbook(depth=5)
            mid     = ob["mid"]
            spread  = ob["spread"]

            # Record price into candle builder
            candle_completed = candles.record_price(mid)
            if candle_completed:
                log.debug(f"New candle closed | candles buffered: {len(candles)}")

            log.info(f"Tick | mid={mid:.4f} spread={spread:.5f} candles={len(candles)}")

            # ── 3. Fetch account state ────────────────────────────────────────
            account = await get_account_state()
            pos     = account["position"]
            collat  = account["collateral"]

            log.info(f"Account | position={pos:.2f} XRP | "
                     f"collateral={collat:.2f} USDC | "
                     f"uPnL={account['unrealized_pnl']:.2f}")

            # ── 4. Check SL/TP for existing position ──────────────────────────
            if pos != 0:
                sl_tp_hit = await check_sl_tp(mid, pos)
                if sl_tp_hit and not dry_run:
                    log.warning(f"Closing position due to {sl_tp_hit.upper()}")
                    close_dir = Direction.SHORT if pos > 0 else Direction.LONG
                    slippage = 0.02
                    worst_px = mid * (1 - slippage) if close_dir == Direction.SHORT \
                               else mid * (1 + slippage)
                    await place_market_order(close_dir, abs(pos), worst_px,
                                            reason=sl_tp_hit.upper())

            # ── 5. Generate strategy signal ───────────────────────────────────
            min_c = strategy.min_candles_required
            if not candles.enough_data(min_c):
                remaining = min_c - len(candles)
                log.info(f"Warming up — need {remaining} more candles "
                         f"({len(candles)}/{min_c})")
            else:
                if not warmup_done:
                    log.success("Warm-up complete — bot is now active!")
                    warmup_done = True

                df = candles.to_dataframe()
                sig = strategy.generate_signal(df, mid, pos, collat)

                log.info(f"Signal | {sig.direction.name} | {sig.reason}")

                await execute_signal(sig, account, dry_run=dry_run)

        except KillSwitchError as e:
            log.critical(f"KILL SWITCH: {e}")
            log.critical("Cancelling all orders and stopping bot...")
            if not dry_run:
                try:
                    await cancel_all()
                except Exception:
                    pass
            break

        except OrderError as e:
            log.error(f"Order error (will retry next tick): {e}")

        except Exception as e:
            log.exception(f"Unexpected error: {e}")

        finally:
            # ── 6. Sleep until next tick ──────────────────────────────────────
            elapsed = time.time() - loop_start
            sleep_t = max(0, settings.POLL_INTERVAL_SECONDS - elapsed)
            if not _shutdown:
                log.debug(f"Sleeping {sleep_t:.1f}s until next tick...")
                await asyncio.sleep(sleep_t)

    # ── Shutdown ───────────────────────────────────────────────────────────────
    log.warning("Bot loop exited — cleaning up...")
    if not dry_run:
        try:
            await cancel_all()
            log.info("All orders cancelled on shutdown")
        except Exception as e:
            log.error(f"Error cancelling orders on shutdown: {e}")
    await close_clients()
    log.info("Bot stopped cleanly.")


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="XRP Trading Bot — Lighter.xyz")
    parser.add_argument("--list-markets", action="store_true",
                        help="List all Lighter markets and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without placing real orders")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logger(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)

    if args.list_markets:
        asyncio.run(list_markets())
        sys.exit(0)

    asyncio.run(run_bot(dry_run=args.dry_run))
