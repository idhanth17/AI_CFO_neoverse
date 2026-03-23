"""
Inventory database tools for the chatbot — async wrappers around SQLAlchemy queries.

Adapted from the feature branch to use the existing async engine
and `Product` model (instead of sync `Inventory` model).

Field mapping:
  Feature branch  →  Existing codebase
  product_name    →  name
  price           →  selling_price
  stock           →  current_stock
  unit            →  unit
"""
from __future__ import annotations

import difflib
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Product
from app.core.logger import logger


# ─── Fuzzy-match threshold (0–1). Raise to require stricter match. ───────────
_FUZZY_THRESHOLD = 0.55


# ─── Read helpers ─────────────────────────────────────────────────────────────

async def get_product_by_name(db: AsyncSession, name: str) -> Optional[Product]:
    """
    Product lookup: first tries SQL LIKE, then falls back to fuzzy matching.
    """
    # ── 1. Fast path: SQL LIKE (exact substring) ─────────────────────────────
    result = await db.execute(
        select(Product)
        .where(Product.name.ilike(f"%{name}%"))
        .where(Product.is_active == True)
    )
    match = result.scalar_one_or_none()
    if match:
        return match

    # ── 2. Fuzzy fallback: score all product names ────────────────────────────
    all_result = await db.execute(
        select(Product).where(Product.is_active == True)
    )
    all_products = list(all_result.scalars().all())
    if not all_products:
        return None

    name_lower = name.lower()
    best_score  = 0.0
    best_match  = None

    for product in all_products:
        pname = product.name.lower()

        # Full name similarity
        score = difflib.SequenceMatcher(None, name_lower, pname).ratio()

        # Also score against each word in the product name
        for word in pname.split():
            if len(word) >= 3:
                word_score = difflib.SequenceMatcher(None, name_lower, word).ratio()
                for query_word in name_lower.split():
                    if len(query_word) >= 3:
                        ws = difflib.SequenceMatcher(None, query_word, word).ratio()
                        word_score = max(word_score, ws)
                score = max(score, word_score)

        if score > best_score:
            best_score = score
            best_match = product

    if best_match and best_score >= _FUZZY_THRESHOLD:
        logger.info(
            f"Fuzzy match: '{name}' → '{best_match.name}' "
            f"(score={best_score:.2f})"
        )
        return best_match

    logger.warning(
        f"No fuzzy match for '{name}' "
        f"(best={best_match.name if best_match else 'none'} @ {best_score:.2f})"
    )
    return None


async def get_all_products(db: AsyncSession) -> List[Product]:
    result = await db.execute(
        select(Product)
        .where(Product.is_active == True)
        .order_by(Product.name)
    )
    return list(result.scalars().all())


async def get_low_stock_products(db: AsyncSession, threshold: int = 20) -> List[Product]:
    result = await db.execute(
        select(Product)
        .where(Product.is_active == True)
        .where(Product.current_stock <= threshold)
        .order_by(Product.current_stock)
    )
    return list(result.scalars().all())


async def get_total_inventory_value(db: AsyncSession) -> float:
    """Sum of (selling_price × current_stock) across all active products."""
    result = await db.execute(
        select(func.sum(Product.selling_price * Product.current_stock))
        .where(Product.is_active == True)
    )
    val = result.scalar()
    return float(val or 0.0)


async def get_stock_for_product(db: AsyncSession, name: str) -> Optional[dict]:
    """Return stock + price for a product matched by name fragment."""
    product = await get_product_by_name(db, name)
    if product is None:
        logger.warning(f"Product not found: '{name}'")
        return None
    return {
        "name": product.name,
        "stock": product.current_stock,
        "price": product.selling_price,
        "unit": product.unit,
        "cost_price": product.cost_price,
    }


async def get_inventory_summary(db: AsyncSession) -> dict:
    """High-level inventory summary statistics."""
    total_products_result = await db.execute(
        select(func.count(Product.id)).where(Product.is_active == True)
    )
    total_products = total_products_result.scalar() or 0

    total_value = await get_total_inventory_value(db)

    low_stock_result = await db.execute(
        select(func.count(Product.id))
        .where(Product.is_active == True)
        .where(Product.current_stock <= Product.reorder_point)
    )
    low_stock_count = low_stock_result.scalar() or 0

    out_of_stock_result = await db.execute(
        select(func.count(Product.id))
        .where(Product.is_active == True)
        .where(Product.current_stock == 0)
    )
    out_of_stock_count = out_of_stock_result.scalar() or 0

    return {
        "total_products": total_products,
        "total_value": round(total_value, 2),
        "low_stock_items": low_stock_count,
        "out_of_stock_items": out_of_stock_count,
    }
