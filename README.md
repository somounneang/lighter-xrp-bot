# XRP Trading Bot — Lighter.xyz

A fully automated, production-ready Python trading bot for the XRP perpetual futures market on [Lighter.xyz](https://lighter.xyz).

## Strategies

| Strategy | Description | Best for |
|---|---|---|
| `trend_following` | EMA-9/21 crossover + RSI filter + ATR stops | Trending markets |
| `mean_reversion` | Bollinger Band bounces + RSI | Ranging markets |
| `combined` (recommended) | Both must agree before entering | All conditions — fewer but higher-quality signals |

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API credentials

# 3. Find your XRP market index
python main.py --list-markets

# 4. Update XRP_MARKET_INDEX in .env, then test
python main.py --dry-run

# 5. Go live
python main.py
```

## Project Structure

```
lighter-xrp-bot/
├── config/settings.py        All configuration (loaded from .env)
├── core/client.py            Lighter SDK client init
├── core/exceptions.py        Custom exceptions
├── market/
│   ├── orderbook.py          Fetch live orderbook & mid price
│   ├── candles.py            Build OHLCV candles from price samples
│   └── account.py            Fetch positions & collateral
├── strategy/
│   ├── base.py               Abstract base + Signal dataclass
│   ├── indicators.py         EMA, RSI, ATR, Bollinger Bands
│   ├── trend_following.py    EMA crossover strategy
│   ├── mean_reversion.py     BB bounce strategy
│   └── combined.py           Confluence of both
├── execution/
│   ├── order_manager.py      Place/cancel/track orders on Lighter
│   └── risk_manager.py       Position limits, kill switch, validation
├── tests/                    pytest unit tests
├── .env.example              Config template
├── requirements.txt
└── main.py                   Entry point
```

## Risk Controls

- **Max position size** — hard cap on XRP held at any time
- **Max order size** — caps each individual order
- **ATR-based stop-loss** — dynamic SL/TP scaled to current volatility
- **Daily loss kill switch** — automatically stops and cancels all orders
- **Risk-per-trade sizing** — only 1% of collateral risked per trade
- **Graceful shutdown** — CTRL+C cancels all open orders cleanly

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `BASE_URL` | Lighter API URL | mainnet |
| `L1_ADDRESS` | Your Ethereum wallet address | required |
| `ACCOUNT_INDEX` | Lighter account index | required |
| `API_KEY_INDEX` | API key index (3–254) | required |
| `API_PRIVATE_KEY` | API private key | required |
| `XRP_MARKET_INDEX` | Market index for XRP-USD perp | required |
| `STRATEGY` | `combined`, `trend_following`, `mean_reversion` | `combined` |
| `MAX_POSITION_SIZE` | Max XRP units in position | 500 |
| `MAX_DAILY_LOSS_USDC` | Kill-switch loss threshold | 50 |
| `RISK_PER_TRADE_PCT` | Fraction of collateral to risk | 0.01 |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## ⚠️ Disclaimer

This bot is for educational purposes. Trading carries significant risk. Test thoroughly on testnet (`https://testnet.zklighter.elliot.ai`) before using real funds.
