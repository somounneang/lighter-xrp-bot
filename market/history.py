"""
market/history.py
-----------------
Pre-loads historical OHLCV candles from Lighter's CandlestickApi on
startup so the bot is ready to trade immediately — zero warm-up wait.

SDK method (confirmed from docs):
  lighter.CandlestickApi(client).candlesticks(
      market_id, resolution, start_timestamp, end_timestamp, count_back
  )

Resolution options (string, in seconds):
  "60"    = 1-minute candles
  "300"   = 5-minute candles
  "900"   = 15-minute candles
  "3600"  = 1-hour candles
"""
from __future__ import annotations

import time
import lighter

from core.client import get_api_client
from market.candles import CandleBuffer, Candle
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


async def preload_candles(buffer: CandleBuffer, count: int = 210) -> int:
    """
    Fetch `count` historical candles and inject them into the CandleBuffer.
    Bot becomes ready to trade instantly on startup.
    Returns number of candles loaded (0 = fell back to live warm-up).
    """
    interval   = buffer._interval       # e.g. 60 or 300
    resolution = str(interval)          # API wants string
    now        = int(time.time())
    start_ts   = now - (interval * count * 2)  # generous lookback window

    log.info(
        f"Fetching {count} historical candles "
        f"(resolution={resolution}s={interval//60}min)..."
    )

    try:
        client = get_api_client()
        api    = lighter.CandlestickApi(client)

        resp = await api.candlesticks(
            market_id=settings.XRP_MARKET_INDEX,
            resolution=resolution,
            start_timestamp=start_ts,
            end_timestamp=now,
            count_back=count,
        )

        # Try known response field names
        candle_list = (
            getattr(resp, "candlesticks", None) or
            getattr(resp, "data",         None) or
            []
        )

        if not candle_list:
            log.warning("No historical candles returned — will warm up from live data")
            return 0

        loaded = 0
        for c in candle_list:
            try:
                o = float(getattr(c, "open",  0))
                h = float(getattr(c, "high",  0))
                l = float(getattr(c, "low",   0))
                cl = float(getattr(c, "close", 0))
                ts = float(getattr(c, "open_time",
                           getattr(c, "timestamp",
                           getattr(c, "time", 0))))
                vol = float(getattr(c, "base_token_volume",
                            getattr(c, "volume", 0)))

                if cl <= 0:
                    continue

                candle = Candle(ts=ts, open=o, high=h, low=l, close=cl, volume=vol)
                buffer._candles.append(candle)
                loaded += 1

            except Exception as e:
                log.debug(f"Skipping malformed candle: {e}")

        if loaded > 0:
            # Sync buffer's live-candle tracking state to last historical close
            last = buffer._candles[-1]
            buffer._open_ts = last.ts + interval
            buffer._open = buffer._high = buffer._low = buffer._last = last.close

        log.success(
            f"✅ Pre-loaded {loaded} candles — "
            f"bot ready immediately, no warm-up needed!"
        )
        return loaded

    except Exception as e:
        log.warning(f"Candle pre-load failed: {e} — falling back to live warm-up")
        return 0


async def debug_candle_response() -> None:
    """
    Run this once if preload fails to see exact API response field names:
      python3 -c "
      import asyncio
      from market.history import debug_candle_response
      asyncio.run(debug_candle_response())
      "
    """
    client = get_api_client()
    api    = lighter.CandlestickApi(client)
    now    = int(time.time())

    resp = await api.candlesticks(
        market_id=settings.XRP_MARKET_INDEX,
        resolution="60",
        start_timestamp=now - 600,
        end_timestamp=now,
        count_back=3,
    )
    print("\n=== CandlestickApi response ===")
    print("Type:", type(resp))
    print("Fields:", [x for x in dir(resp) if not x.startswith("_")])
    for attr in ["candlesticks", "data", "items", "ohlcv"]:
        val = getattr(resp, attr, None)
        if val:
            print(f"\nFound list at resp.{attr}:")
            c = val[0]
            print("  Candle type:", type(c))
            print("  Candle fields:", [x for x in dir(c) if not x.startswith("_")])
            print("  Candle value:", c)
            break
    print("===============================\n")
