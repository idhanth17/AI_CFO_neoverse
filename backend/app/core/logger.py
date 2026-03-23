"""
Loguru-based logger configuration.
Import `logger` from this module throughout the application.
"""
import sys
from loguru import logger
from app.core.config import settings

# Remove the default handler
logger.remove()

# Console handler — human-readable
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
           "<level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True,
)

__all__ = ["logger"]
