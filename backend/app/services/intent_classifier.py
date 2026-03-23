"""
Intent Classifier — centralised keyword-based intent detection.

Supports English, Tamil (Unicode), and Tanglish queries.
Intents are checked in priority order to avoid ambiguity.
"""
from __future__ import annotations

import re
from typing import Tuple

from app.core.logger import logger


# ── Keyword lists per intent ──────────────────────────────────────────────────
# Include English, Tamil Unicode, and Tanglish variants.

_GREETING_KEYWORDS = [
    # English
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "welcome", "namaste",
    # Tanglish
    "vanakkam", "vaanga", "vango", "ayya", "anna",
    # Tamil Unicode
    "வணக்கம்", "நமஸ்தே",
]

_PRICE_KEYWORDS = [
    # English
    "price", "cost", "rate", "how much does", "how much is", "what is the price",
    "worth", "charge", "amount",
    # Tanglish
    "vilai", "vila", "enna vilai", "vilai enna", "rate enna",
    "enna rate", "kattanam", "kittu",
    # Tamil Unicode
    "விலை", "கட்டணம்", "மதிப்பு", "விலை என்ன",
]

_STOCK_KEYWORDS = [
    # English
    "stock", "quantity", "how many", "available", "left", "remaining",
    "units", "count", "inventory",
    # Tanglish
    "evlo", "evvlo", "evvalavu", "iruku", "irukku", "sollu",
    "stock evlo", "quantity evlo", "ethanai iruku",
    # Tamil Unicode
    "எவ்வளவு", "இருக்கு", "இருக்கிறது", "சொல்லு", "எண்ணிக்கை",
]

_PRODUCT_KEYWORDS = [
    # English
    "tell me about", "what is", "details", "info", "information",
    "describe", "show me",
    # Tanglish
    "sollu", "paaru", "paarungo", "enna solluv", "vilaivu",
    # Tamil Unicode
    "விவரம்", "பொருள்", "தகவல்",
]

_LOW_STOCK_KEYWORDS = [
    # English
    "low stock", "out of stock", "shortage", "running out", "nearly empty",
    "reorder", "less stock",
    # Tanglish
    "kammiya", "kammiya iruku", "thadai", "stock illai",
    "kureivana", "thadaipadu",
    # Tamil Unicode
    "குறைவான", "குறைவு", "இல்லை",
]

_ANALYTICS_KEYWORDS = [
    # English
    "summary", "overview", "report", "analytics", "total", "all products",
    "full list", "category", "which products", "top product", "best selling",
    "highest", "breakdown",
    # Tanglish
    "ellam", "ellam sollu", "total sollu", "sabha porul",
    "munnetru", "category sollu",
    # Tamil Unicode
    "மொத்தம்", "எல்லாம்", "சுருக்கம்", "அறிக்கை", "வகை",
]


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears in *text* (case-insensitive)."""
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


# ── Public API ────────────────────────────────────────────────────────────────

# Intent constants (importable by other modules)
INTENT_GREETING      = "greeting"
INTENT_PRICE         = "price_query"
INTENT_STOCK         = "stock_query"
INTENT_PRODUCT       = "product_query"
INTENT_LOW_STOCK     = "low_stock_query"
INTENT_ANALYTICS     = "analytics_query"
INTENT_UNKNOWN       = "unknown"


def detect_intent(text: str) -> str:
    """
    Classify the intent of a natural-language query.

    Priority order (most specific first):
    1. greeting
    2. low_stock_query  (more specific than stock_query)
    3. analytics_query
    4. price_query
    5. stock_query
    6. product_query
    7. unknown

    Returns one of the INTENT_* constants.
    """
    if not text or not text.strip():
        return INTENT_UNKNOWN

    if _contains_any(text, _GREETING_KEYWORDS):
        logger.debug("Intent → greeting")
        return INTENT_GREETING

    if _contains_any(text, _LOW_STOCK_KEYWORDS):
        logger.debug("Intent → low_stock_query")
        return INTENT_LOW_STOCK

    if _contains_any(text, _ANALYTICS_KEYWORDS):
        logger.debug("Intent → analytics_query")
        return INTENT_ANALYTICS

    if _contains_any(text, _PRICE_KEYWORDS):
        logger.debug("Intent → price_query")
        return INTENT_PRICE

    if _contains_any(text, _STOCK_KEYWORDS):
        logger.debug("Intent → stock_query")
        return INTENT_STOCK

    if _contains_any(text, _PRODUCT_KEYWORDS):
        logger.debug("Intent → product_query")
        return INTENT_PRODUCT

    logger.debug("Intent → unknown")
    return INTENT_UNKNOWN
