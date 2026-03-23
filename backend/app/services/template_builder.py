"""
Template Builder — constructs authoritative Tamil / English response strings
directly from database data.

CRITICAL RULE: Numbers, prices, and product names are ALWAYS sourced from
the `product_data` dict (which comes from the database). The LLM never
sees raw numbers — it only polishes the final string if needed.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.logger import logger


# ─── Language selection helpers ───────────────────────────────────────────────

def _is_tamil_mode(language: str) -> bool:
    """Return True for Tamil script OR Tanglish responses."""
    return language in ("ta", "tanglish")


# ─── Per-intent template functions ───────────────────────────────────────────

def build_price_response(product: dict[str, Any], language: str) -> str:
    name  = product.get("name",  product.get("product_name", "Product"))
    price = product.get("price", product.get("selling_price", 0))
    unit  = product.get("unit",  "piece")

    if _is_tamil_mode(language):
        return f"{name} விலை ₹{price} ஒரு {unit}க்கு."
    return f"The price of {name} is ₹{price} per {unit}."


def build_stock_response(product: dict[str, Any], language: str) -> str:
    name  = product.get("name",  product.get("product_name", "Product"))
    stock = product.get("stock", product.get("current_stock", 0))
    unit  = product.get("unit",  "piece")

    if _is_tamil_mode(language):
        return f"{name} இப்போது {stock} {unit} இருக்கு."
    return f"{name} currently has {stock} {unit} in stock."


def build_product_response(product: dict[str, Any], language: str) -> str:
    name  = product.get("name",  product.get("product_name", "Product"))
    price = product.get("price", product.get("selling_price", 0))
    stock = product.get("stock", product.get("current_stock", 0))
    unit  = product.get("unit",  "piece")

    if _is_tamil_mode(language):
        return (
            f"{name}: விலை ₹{price} ஒரு {unit}க்கு, "
            f"இப்போது {stock} {unit} இருக்கு."
        )
    return (
        f"{name}: ₹{price} per {unit}, "
        f"{stock} {unit} available in stock."
    )


def build_low_stock_response(products: list[dict[str, Any]], language: str) -> str:
    if not products:
        if _is_tamil_mode(language):
            return "அனைத்து பொருட்களும் போதுமான அளவு இருக்கின்றன."
        return "All products have sufficient stock."

    if _is_tamil_mode(language):
        lines = ["குறைவான stock உள்ள பொருட்கள்:"]
        for p in products:
            name  = p.get("name", p.get("product_name", "?"))
            stock = p.get("stock", p.get("current_stock", 0))
            unit  = p.get("unit", "piece")
            lines.append(f"• {name}: {stock} {unit} மட்டுமே இருக்கு.")
        return "\n".join(lines)

    lines = ["Products with low stock:"]
    for p in products:
        name  = p.get("name", p.get("product_name", "?"))
        stock = p.get("stock", p.get("current_stock", 0))
        unit  = p.get("unit", "piece")
        lines.append(f"• {name}: only {stock} {unit} remaining.")
    return "\n".join(lines)


def build_analytics_response(summary: dict[str, Any], language: str) -> str:
    total_products = summary.get("total_products", 0)
    total_value    = summary.get("total_value", 0.0)
    low_stock      = summary.get("low_stock_items", 0)

    if _is_tamil_mode(language):
        return (
            f"மொத்தம் {total_products} பொருட்கள் உள்ளன. "
            f"மொத்த மதிப்பு ₹{total_value:,.0f}. "
            f"{low_stock} பொருட்கள் குறைவான stock-ல் உள்ளன."
        )
    return (
        f"Total products: {total_products}. "
        f"Inventory value: ₹{total_value:,.0f}. "
        f"{low_stock} items are low on stock."
    )


def build_greeting_response(language: str) -> str:
    if _is_tamil_mode(language):
        return "வணக்கம்! என்ன உதவி வேண்டும்?"
    return "Hello! How can I help you today?"


def build_not_found_response(language: str) -> str:
    if _is_tamil_mode(language):
        return "மன்னிக்கவும், அந்த பொருள் கிடைக்கவில்லை."
    return "Sorry, that product was not found in our inventory."


def build_unknown_response(language: str) -> str:
    if _is_tamil_mode(language):
        return "மன்னிக்கவும், உங்கள் கேள்வி புரியவில்லை. விலை அல்லது stock பற்றி கேளுங்கள்."
    return "Sorry, I didn't understand that. Please ask about price or stock."


# ─── Dispatcher ───────────────────────────────────────────────────────────────

def build_template(
    intent: str,
    language: str,
    product: Optional[dict[str, Any]] = None,
    products: Optional[list[dict[str, Any]]] = None,
    summary: Optional[dict[str, Any]] = None,
) -> str:
    from app.services.intent_classifier import (
        INTENT_GREETING, INTENT_PRICE, INTENT_STOCK,
        INTENT_PRODUCT, INTENT_LOW_STOCK, INTENT_ANALYTICS,
    )

    if intent == INTENT_GREETING:
        return build_greeting_response(language)

    if intent == INTENT_PRICE:
        if product:
            return build_price_response(product, language)
        return build_not_found_response(language)

    if intent == INTENT_STOCK:
        if product:
            return build_stock_response(product, language)
        return build_not_found_response(language)

    if intent == INTENT_PRODUCT:
        if product:
            return build_product_response(product, language)
        return build_not_found_response(language)

    if intent == INTENT_LOW_STOCK:
        return build_low_stock_response(products or [], language)

    if intent == INTENT_ANALYTICS:
        if summary:
            return build_analytics_response(summary, language)
        return build_not_found_response(language)

    # unknown
    return build_unknown_response(language)
