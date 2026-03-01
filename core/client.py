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
_market_meta: dict | None = None


def get_signer() -> lighter.SignerClient:
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
    global _api_client
    if _api_client is None:
        config = lighter.Configuration(host=settings.BASE_URL)
        _api_client = lighter.ApiClient(config)
        log.success("ApiClient ready")
    return _api_client


async def close_clients() -> None:
    global _api_client
    if _api_client:
        await _api_client.close()
        log.info("ApiClient closed")


async def get_market_meta(market_index: int | None = None) -> dict:
    """
    Fetch and cache market metadata for the XRP market.

    Confirmed real response shape from live API:
        details.order_book_details[0]  →  PerpsOrderBookDetail
            .symbol              e.g. "XRP"
            .market_id           int (7 for XRP)
            .size_decimals       e.g. 1
            .price_decimals      e.g. 5
            .min_base_amount     e.g. "5.0"
            .last_trade_price    float
    """
    global _market_meta
    if _market_meta is None:
        idx = market_index if market_index is not None else settings.XRP_MARKET_INDEX
        client = get_api_client()
        order_api = lighter.OrderApi(client)
        details = await order_api.order_book_details(market_id=idx)

        ob = details.order_book_details[0]

        size_dec  = int(ob.size_decimals)
        price_dec = int(ob.price_decimals)

        _market_meta = {
            "base_size":       10 ** size_dec,
            "base_price":      10 ** price_dec,
            "size_decimals":   size_dec,
            "price_decimals":  price_dec,
            "min_base_amount": float(ob.min_base_amount),
            "symbol":          ob.symbol,
            "market_id":       int(ob.market_id),
            "last_price":      float(ob.last_trade_price),
        }
        log.info(f"Market meta: {_market_meta}")
    return _market_meta
