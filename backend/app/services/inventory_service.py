"""
Inventory Service
-----------------
Core stock-management logic implementing the two-directional inventory model:

  stock += purchase_quantity   (supplier invoice processed)
  stock -= sale_quantity       (customer sale recorded)

Also handles:
  - Product lookup / fuzzy name matching
  - Auto-creating unknown products encountered in invoices
  - Updating cost price on new purchases (latest-price model)
"""

from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import Product, InvoiceItem, SaleItem


async def find_product_by_name(
    db: AsyncSession, name: str
) -> Optional[Product]:
    """Find a product by exact name (case-insensitive)."""
    result = await db.execute(
        select(Product).where(
            func.lower(Product.name) == name.strip().lower(),
            Product.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def find_or_create_product(
    db: AsyncSession,
    name: str,
    cost_price: float = 0.0,
    gst_rate: float = 0.0,
    custom_profit_margin: float = 20.0,
) -> Tuple[Product, bool]:
    """
    Finds an existing product or creates a new one.
    Returns (product, created: bool).
    """
    product = await find_product_by_name(db, name)
    if product:
        return product, False

    product = Product(
        name=name.strip(),
        cost_price=cost_price,
        selling_price=round(cost_price * (1 + custom_profit_margin / 100), 2),
        gst_rate=gst_rate,
        current_stock=0.0,
        reorder_point=5.0,
        safety_stock=2.0,
        lead_time_days=3,
    )
    db.add(product)
    await db.flush()  # get the ID without committing
    logger.info(f"Auto-created product: {name!r} (id={product.id})")
    return product, True


async def apply_purchase(
    db: AsyncSession,
    invoice_item: InvoiceItem,
    custom_profit_margin: float = 20.0,
) -> Product:
    """
    Apply a purchase (supplier invoice item) to inventory.
    stock += item.quantity | cost_price = latest purchase price
    """
    product, created = await find_or_create_product(
        db,
        name=invoice_item.raw_name,
        cost_price=invoice_item.unit_price,
        gst_rate=invoice_item.gst_rate,
        custom_profit_margin=custom_profit_margin,
    )

    invoice_item.product_id = product.id

    prev_stock = product.current_stock
    product.current_stock = round(product.current_stock + invoice_item.quantity, 3)
    product.cost_price     = invoice_item.unit_price
    product.gst_rate       = invoice_item.gst_rate
    
    # Update selling price based on the selected profit margin
    if invoice_item.unit_price > 0:
        product.selling_price = round(invoice_item.unit_price * (1 + custom_profit_margin / 100), 2)

    logger.info(
        f"Purchase applied: {product.name} | "
        f"stock {prev_stock:.2f} → {product.current_stock:.2f} "
        f"(+{invoice_item.quantity})"
    )
    return product


async def apply_sale(
    db: AsyncSession,
    sale_item: SaleItem,
) -> Optional[Product]:
    """
    Apply a customer sale to inventory.
    stock -= item.quantity

    If product not found: log a warning and skip (don't create phantom products).
    """
    product = await find_product_by_name(db, sale_item.raw_name)

    if not product:
        logger.warning(
            f"Sale item '{sale_item.raw_name}' not found in product catalogue — "
            f"stock not deducted"
        )
        return None

    sale_item.product_id  = product.id
    sale_item.unit_price  = product.selling_price
    sale_item.total_amount = round(product.selling_price * sale_item.quantity, 2)

    prev_stock = product.current_stock

    if sale_item.quantity > product.current_stock:
        logger.warning(
            f"Selling {sale_item.quantity} of '{product.name}' "
            f"but only {product.current_stock:.2f} in stock — going negative"
        )

    product.current_stock = round(product.current_stock - sale_item.quantity, 3)

    logger.info(
        f"Sale applied: {product.name} | "
        f"stock {prev_stock:.2f} → {product.current_stock:.2f} "
        f"(-{sale_item.quantity})"
    )
    return product


async def get_all_products(db: AsyncSession) -> List[Product]:
    result = await db.execute(
        select(Product)
        .where(Product.is_active == True)  # noqa: E712
        .order_by(Product.name)
    )
    return list(result.scalars().all())


async def get_low_stock_products(db: AsyncSession) -> List[Product]:
    """Return products where current_stock <= reorder_point."""
    result = await db.execute(
        select(Product).where(
            Product.is_active == True,  # noqa: E712
            Product.current_stock <= Product.reorder_point,
        )
    )
    return list(result.scalars().all())
