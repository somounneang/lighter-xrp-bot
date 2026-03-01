"""
main.py
-------
XRP Trading Bot for Lighter.xyz

Strategies (set STRATEGY in .env):
  trend_following   EMA crossover + RSI + ATR stops
  mean_reversion    Bollinger Band bounces + RSI filter
  combined          TF + MR must agree
  ut_bot            UT Bot Alert (ATR trailing stop + EMA-200 filter)
  super_combined    ALL THREE must agree (recommended — highest quality signals)

Run:
    python main.py                  # Live trading
    python main.py --list-markets   # Show all markets
    python main.py --dry-run        # Simulate without real orders
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
from market.orderbook import fetch_orderbook
from market.candles import get_candle_buffer
from market.account import get_account_state
from strategy.base import Direction, Signal
from strategy.trend_following import TrendFollowingStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.combined import CombinedStrategy
from strategy.ut_bot import UTBotStrategy
from strategy.super_combined import SuperCombinedStrategy
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
    strategies = {
        "trend_following":  (TrendFollowingStrategy,  "Trend Following (EMA + RSI + ATR)"),
        "mean_reversion":   (MeanReversionStrategy,   "Mean Reversion (Bollinger Bands + RSI)"),
        "combined":         (CombinedStrategy,         "Combined (TF + MR confluence)"),
        "ut_bot":           (UTBotStrategy,            "UT Bot Alert (ATR trail + EMA-200)"),
        "super_combined":   (SuperCombinedStrategy,    "🔥 Super Combined (TF + MR + UT Bot)"),
    }
    cls, label = strategies.get(name, (SuperCombinedStrategy, "🔥 Super Combined (default)"))
    log.info(f"Strategy: {label}")
    return cls()


# ── Market listing ─────────────────────────────────────────────────────────────

async def list_markets():
    client = get_api_client()
    order_api = lighter.OrderApi(client)
    resp = await order_api.order_books()
    print("\n" + "─" * 60)
    print(f"{'market_id':<12} {'Symbol':<20} {'Status':<12} {'Last Price'}")
    print("─" * 60)
    for ob in getattr(resp, "order_books", []):
        print(
            f"{str(getattr(ob, 'market_id', '?')):<12} "
            f"{str(getattr(ob, 'symbol', '?')):<20} "
            f"{str(getattr(ob, 'status', 'active')):<12} "
            f"{getattr(ob, 'last_trade_price', '?')}"
        )
    print("─" * 60)
    print("\nSet XRP_MARKET_INDEX=7 in your .env\n")
    await close_clients()


# ── Signal execution ───────────────────────────────────────────────────────────

async def execute_signal(sig: Signal, account: dict, dry_run: bool = False) -> None:
    current_pos = account["position"]

    if sig.direction == Direction.FLAT and sig.size_xrp == 0:
        log.debug(f"No action | {sig.reason}")
        return

    # ── Close existing position ───────────────────────────────────────────────
    if sig.direction == Direction.FLAT and abs(current_pos) > 0:
        close_dir  = Direction.SHORT if current_pos > 0 else Direction.LONG
        close_size = abs(current_pos)
        slippage   = 0.02
        worst_px   = (sig.entry_price * (1 - slippage) if close_dir == Direction.SHORT
                      else sig.entry_price * (1 + slippage))
        log.info(f"[CLOSE] {close_dir.name} {close_size:.1f} XRP @ ~{sig.entry_price:.5f} | {sig.reason}")
        if not dry_run:
            await place_market_order(close_dir, close_size, worst_px, reason=sig.reason)
        else:
            log.info("[DRY-RUN] Would close position")
        return

    # ── Open new position ─────────────────────────────────────────────────────
    if sig.direction in (Direction.LONG, Direction.SHORT) and current_pos == 0:
        try:
            validated = rm.validate_signal(sig, current_pos)
        except RiskLimitError as e:
            log.warning(f"Risk rejected: {e}")
            return

        log.info(
            f"[ENTRY] {validated.direction.name} {validated.size_xrp:.1f} XRP "
            f"@ {validated.entry_price:.5f} | "
            f"SL={validated.stop_loss:.5f} TP={validated.take_profit:.5f} | "
            f"{validated.reason}"
        )
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


# ── Main bot loop ──────────────────────────────────────────────────────────────

async def run_bot(dry_run: bool = False) -> None:
    global _shutdown

    setup_logger(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)

    log.info("=" * 60)
    log.info("  XRP Trading Bot — Lighter.xyz")
    log.info(f"  Strategy      : {settings.STRATEGY}")
    log.info(f"  Market ID     : {settings.XRP_MARKET_INDEX} (XRP)")
    log.info(f"  Candle        : {settings.CANDLE_INTERVAL_SECONDS}s "
             f"({settings.CANDLE_INTERVAL_SECONDS//60}min)")
    log.info(f"  Poll interval : {settings.POLL_INTERVAL_SECONDS}s")
    log.info(f"  Dry-run       : {dry_run}")
    log.info("=" * 60)

    _ = get_signer()
    _ = get_api_client()
    meta = await get_market_meta()
    log.info(
        f"Market: {meta['symbol']} | "
        f"min_amount={meta['min_base_amount']} XRP | "
        f"last_price={meta['last_price']}"
    )

    strategy    = build_strategy()
    candles     = get_candle_buffer(interval_seconds=settings.CANDLE_INTERVAL_SECONDS)
    warmup_done = False

    log.info(
        f"Warm-up needed: {strategy.min_candles_required} candles × "
        f"{settings.CANDLE_INTERVAL_SECONDS//60}min = "
        f"~{strategy.min_candles_required * settings.CANDLE_INTERVAL_SECONDS // 60} minutes"
    )

    while not _shutdown:
        loop_start = time.time()

        try:
            # ── Daily reset ───────────────────────────────────────────────────
            if time.time() - rm.get_state().daily_start_ts > 86_400:
                rm.reset_daily_pnl()

            # ── Market data ───────────────────────────────────────────────────
            ob     = await fetch_orderbook(depth=5)
            mid    = ob["mid"]
            spread = ob["spread"]
            candles.record_price(mid)

            log.info(
                f"Tick | XRP={mid:.5f} USDC | "
                f"spread={spread:.5f} | "
                f"candles={len(candles)}/{strategy.min_candles_required}"
            )

            # ── Account state ─────────────────────────────────────────────────
            account = await get_account_state()
            pos     = account["position"]
            collat  = account["collateral"]

            log.info(
                f"Account | pos={pos:.1f} XRP | "
                f"collateral={collat:.2f} USDC | "
                f"uPnL={account['unrealized_pnl']:.4f} | "
                f"rPnL={account['realized_pnl']:.4f}"
            )

            # ── SL/TP monitor ─────────────────────────────────────────────────
            if pos != 0:
                sl_tp_hit = await check_sl_tp(mid, pos)
                if sl_tp_hit and not dry_run:
                    log.warning(f"{sl_tp_hit.upper()} hit — closing position")
                    close_dir = Direction.SHORT if pos > 0 else Direction.LONG
                    worst_px  = (mid * 0.98 if close_dir == Direction.SHORT else mid * 1.02)
                    await place_market_order(close_dir, abs(pos), worst_px,
                                             reason=sl_tp_hit.upper())

            # ── Strategy signal ───────────────────────────────────────────────
            if not candles.enough_data(strategy.min_candles_required):
                remaining = strategy.min_candles_required - len(candles)
                mins_left = remaining * settings.CANDLE_INTERVAL_SECONDS // 60
                log.info(f"Warming up | {remaining} candles left (~{mins_left} min)")
            else:
                if not warmup_done:
                    log.success("✅ Warm-up complete — bot is now ACTIVE!")
                    warmup_done = True

                df  = candles.to_dataframe()
                sig = strategy.generate_signal(df, mid, pos, collat)
                log.info(f"Signal | {sig.direction.name} | {sig.reason}")
                await execute_signal(sig, account, dry_run=dry_run)

        except KillSwitchError as e:
            log.critical(f"KILL SWITCH: {e}")
            if not dry_run:
                try:
                    await cancel_all()
                except Exception:
                    pass
            break

        except OrderError as e:
            log.error(f"Order error (retrying next tick): {e}")

        except Exception as e:
            log.exception(f"Unexpected error: {e}")

        finally:
            elapsed = time.time() - loop_start
            sleep_t = max(0, settings.POLL_INTERVAL_SECONDS - elapsed)
            if not _shutdown:
                await asyncio.sleep(sleep_t)

    log.warning("Bot shutting down...")
    if not dry_run:
        try:
            await cancel_all()
        except Exception as e:
            log.error(f"Shutdown cancel error: {e}")
    await close_clients()
    log.info("Bot stopped cleanly.")


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="XRP Trading Bot — Lighter.xyz")
    parser.add_argument("--list-markets", action="store_true",
                        help="List all Lighter markets and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate signals without placing real orders")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logger(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)

    if args.list_markets:
        asyncio.run(list_markets())
        sys.exit(0)

    asyncio.run(run_bot(dry_run=args.dry_run))
