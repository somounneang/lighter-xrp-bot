"""
core/client.py
--------------
Initializes the Lighter SignerClient (for placing orders) and the
read-only ApiClient (for market/account data).

Only ONE instance of each is created for the lifetime of the bot.
"""
import lighter
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)

_signer: lighter.SignerClient | None = None
_api_client: lighter.ApiClient | None = None

# Market metadata cached after first fetch
_market_meta: dict | None = None


def get_signer() -> lighter.SignerClient:
    """Return (or lazily initialise) the SignerClient."""
    global _signer
    if _signer is None:
        log.info(f"Initialising SignerClient → {settings.BASE_URL}")
        _signer = lighter.SignerClient(
            url=settings.BASE_URL,
            api_private_keys={settings.API_KEY_INDEX: settings.API_PRIVATE_KEY},
            account_index=settings.ACCOUNT_INDEX,
        )
        log.success("SignerClient ready")
    return _signer


def get_api_client() -> lighter.ApiClient:
    """Return (or lazily initialise) the read-only ApiClient."""
    global _api_client
    if _api_client is None:
        config = lighter.Configuration(host=settings.BASE_URL)
        _api_client = lighter.ApiClient(config)
        log.success("ApiClient ready")
    return _api_client


async def close_clients() -> None:
    """Gracefully close both clients on shutdown."""
    global _api_client
    if _api_client:
        await _api_client.close()
        log.info("ApiClient closed")


async def get_market_meta(market_index: int | None = None) -> dict:
    """
    Fetch and cache market metadata (base_size, base_price tick units).
    Returns metadata for XRP_MARKET_INDEX by default.

    Uses lighter.OrderApi.order_book_details() — the correct SDK method.
    """
    global _market_meta
    if _market_meta is None:
        idx = market_index if market_index is not None else settings.XRP_MARKET_INDEX
        client = get_api_client()
        order_api = lighter.OrderApi(client)
        # order_book_details accepts by="index" and value=str(market_index)
        details = await order_api.order_book_details(by="index", value=str(idx))

        # The response object contains a list of order_books; grab index 0
        ob = details.order_books[0] if hasattr(details, "order_books") else details

        _market_meta = {
            "base_size":  int(ob.base_size),    # lot size multiplier
            "base_price": int(ob.quote_size),   # tick size multiplier (quote_size = price tick)
            "symbol":     ob.symbol,
        }
        log.info(f"Market meta fetched: {_market_meta}")
    return _market_meta
