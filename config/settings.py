"""
config/settings.py
------------------
Central configuration loaded from .env file.
All other modules import from here — never from os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Missing required env var: {key}")
    return val


def _get(key: str, default=None):
    return os.getenv(key, default)


# ── Connection ────────────────────────────────────────────────────────────────
BASE_URL: str = _get("BASE_URL", "https://mainnet.zklighter.elliot.ai")

# ── Account ───────────────────────────────────────────────────────────────────
L1_ADDRESS: str         = _require("L1_ADDRESS")
ACCOUNT_INDEX: int      = int(_require("ACCOUNT_INDEX"))
API_KEY_INDEX: int      = int(_require("API_KEY_INDEX"))
API_PRIVATE_KEY: str    = _require("API_PRIVATE_KEY")

# ── Market ────────────────────────────────────────────────────────────────────
XRP_MARKET_INDEX: int   = int(_get("XRP_MARKET_INDEX", "5"))

# ── Risk ──────────────────────────────────────────────────────────────────────
MAX_POSITION_SIZE: float    = float(_get("MAX_POSITION_SIZE", "500"))
MAX_DAILY_LOSS_USDC: float  = float(_get("MAX_DAILY_LOSS_USDC", "50"))
MAX_ORDER_SIZE_XRP: float   = float(_get("MAX_ORDER_SIZE_XRP", "100"))
RISK_PER_TRADE_PCT: float   = float(_get("RISK_PER_TRADE_PCT", "0.01"))

# ── Strategy ──────────────────────────────────────────────────────────────────
STRATEGY: str               = _get("STRATEGY", "combined")
POLL_INTERVAL_SECONDS: int  = int(_get("POLL_INTERVAL_SECONDS", "15"))

# Trend following
EMA_FAST: int               = int(_get("EMA_FAST", "9"))
EMA_SLOW: int               = int(_get("EMA_SLOW", "21"))
RSI_PERIOD: int             = int(_get("RSI_PERIOD", "14"))
RSI_OVERBOUGHT: float       = float(_get("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD: float         = float(_get("RSI_OVERSOLD", "30"))
ATR_PERIOD: int             = int(_get("ATR_PERIOD", "14"))
ATR_SL_MULTIPLIER: float    = float(_get("ATR_SL_MULTIPLIER", "1.5"))
ATR_TP_MULTIPLIER: float    = float(_get("ATR_TP_MULTIPLIER", "2.5"))

# Mean reversion
BB_PERIOD: int              = int(_get("BB_PERIOD", "20"))
BB_STD_DEV: float           = float(_get("BB_STD_DEV", "2.0"))
BB_MIN_SQUEEZE: float       = float(_get("BB_MIN_SQUEEZE", "0.005"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str  = _get("LOG_LEVEL", "INFO")
LOG_FILE: str   = _get("LOG_FILE", "logs/bot.log")
