"""core/exceptions.py — Custom exception hierarchy."""


class BotError(Exception):
    """Base for all bot errors."""


class RiskLimitError(BotError):
    """Raised when an action would breach a risk rule."""


class OrderError(BotError):
    """Raised on order placement / cancellation failure."""


class MarketDataError(BotError):
    """Raised when market data is missing or malformed."""


class KillSwitchError(BotError):
    """Raised by the risk manager to halt all trading immediately."""
