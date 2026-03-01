"""
utils/logger.py
---------------
Centralized logger using loguru.  One call to setup_logger() wires up
console + rotating-file output. Every module gets a named logger via
`from utils.logger import get_logger; log = get_logger(__name__)`.
"""
import sys
import os
from loguru import logger as _logger

_configured = False


def setup_logger(log_level: str = "INFO", log_file: str = "logs/bot.log") -> None:
    global _configured
    if _configured:
        return

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    _logger.remove()  # Remove default handler

    # Console — colorful
    _logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        colorize=True,
    )

    # File — rotating 10 MB, keep 7 days
    _logger.add(
        log_file,
        level=log_level,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    )

    _configured = True


def get_logger(name: str = "bot"):
    return _logger.bind(name=name)
