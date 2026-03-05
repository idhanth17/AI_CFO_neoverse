"""
Inventory Routes — /api/inventory
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import Product
from app.schemas.schemas import ProductCreate, ProductUpdate, ProductOut
from app.services.inventory_service import get_all_products, get_low_stock_products

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


@router.get("/", response_model=List[ProductOut])
async def list_products(db: AsyncSession = Depends(get_db)):
    """List all active products with current stock levels."""
    return await get_all_products(db)


@router.get("/low-stock", response_model=List[ProductOut])
async def low_stock_alerts(db: AsyncSession = Depends(get_db)):
    """Products where current_stock <= reorder_point."""
    return await get_low_stock_products(db)


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def add_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
):
    """Manually add a new product to the catalogue."""
    # Check for duplicate name
    existing = await db.execute(
        select(Product).where(
            Product.name.ilike(payload.name.strip())
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product '{payload.name}' already exists.",
        )

    product = Product(**payload.model_dump())
    db.add(product)
    await db.flush()
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single product by ID."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product #{product_id} not found")
    return product


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update product configuration (prices, thresholds, stock level).
    Only provided fields are updated (PATCH semantics).
    """
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product #{product_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Soft-delete a product (sets is_active=False)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product #{product_id} not found")
    product.is_active = False
