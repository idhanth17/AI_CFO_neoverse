"""
Analytics Routes — /api/analytics
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import Product, Invoice, Sale
from app.schemas.schemas import (
    ProfitSummary, DemandForecast, RestockRecommendation,
    GSTSummary, DashboardResponse,
)
from app.agents.analytics_agents import (
    profit_agent, demand_agent, restock_agent, gst_tool
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/profit", response_model=List[ProfitSummary])
async def profit_analysis(db: AsyncSession = Depends(get_db)):
    """
    Product-level gross profit and margin analysis.
    Sorted by gross profit (highest first).
    """
    return await profit_agent.run(db)


@router.get("/demand", response_model=List[DemandForecast])
async def demand_forecast(db: AsyncSession = Depends(get_db)):
    """
    7-day and 30-day demand forecasts using Moving Average + Linear Regression.
    Products with stockout risk appear first.
    """
    return await demand_agent.run(db)


@router.get("/restock", response_model=List[RestockRecommendation])
async def restock_recommendations(db: AsyncSession = Depends(get_db)):
    """
    Optimal reorder quantities per product.
    Urgency: critical → soon → ok.
    """
    # Run demand first so restock can use real forecasts
    forecasts = await demand_agent.run(db)
    return await restock_agent.run(db, demand_forecasts=forecasts)


@router.get("/gst", response_model=List[GSTSummary])
async def gst_summary(
    year:  Optional[int] = Query(None, description="Filter by year (YYYY)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month (1-12)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Monthly input GST (taxes paid on supplier purchases) summary.
    Useful for GST filing and compliance.
    """
    return await gst_tool.run(db, year=year, month=month)


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(db: AsyncSession = Depends(get_db)):
    """
    Combined dashboard snapshot — runs all four agents in sequence
    and returns everything the React frontend needs in a single call.
    """
    # Counts
    total_products = (await db.execute(
        select(func.count()).where(Product.is_active == True)  # noqa: E712
    )).scalar_one()

    low_stock_count = (await db.execute(
        select(func.count()).where(
            Product.is_active == True,  # noqa: E712
            Product.current_stock <= Product.reorder_point,
        )
    )).scalar_one()

    total_invoices = (await db.execute(select(func.count(Invoice.id)))).scalar_one()
    total_sales    = (await db.execute(select(func.count(Sale.id)))).scalar_one()

    # Revenue (sum of processed sales)
    total_revenue = (await db.execute(
        select(func.coalesce(func.sum(Sale.total_amount), 0.0))
        .where(Sale.status == "processed")
    )).scalar_one()

    # Purchases (sum of processed invoices)
    total_purchases = (await db.execute(
        select(func.coalesce(func.sum(Invoice.total_amount), 0.0))
        .where(Invoice.status == "processed")
    )).scalar_one()

    # Run all agents
    profit_data   = await profit_agent.run(db)
    demand_data   = await demand_agent.run(db)
    restock_data  = await restock_agent.run(db, demand_forecasts=demand_data)
    gst_data      = await gst_tool.run(db)

    return DashboardResponse(
        total_products=total_products,
        low_stock_count=low_stock_count,
        total_invoices=total_invoices,
        total_sales=total_sales,
        total_revenue=float(total_revenue),
        total_purchases=float(total_purchases),
        profit_summary=profit_data,
        demand_forecasts=demand_data,
        restock_recs=restock_data,
        gst_summary=gst_data,
    )
