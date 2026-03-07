"""
AI Analytics Agents
-------------------
Four analytics modules operating on the SQLite data:

1. ProfitIntelligenceAgent  — product-level margin analysis (Pandas)
2. DemandPredictionAgent    — moving average + linear regression (Scikit-Learn)
3. RestockRecommendationAgent — optimal reorder qty calculation
4. GSTSummaryTool           — monthly GST aggregation
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import Product, InvoiceItem, SaleItem, Sale, Invoice
from app.schemas.schemas import (
    ProfitSummary, DemandForecast, RestockRecommendation, GSTSummary
)


# ═══════════════════════════════════════════════════════
# 1. PROFIT INTELLIGENCE AGENT
# ═══════════════════════════════════════════════════════

class ProfitIntelligenceAgent:
    """
    Calculates product-level gross profit and margin using Pandas.
    Compares selling price with cost price across all recorded sales.
    """

    async def run(self, db: AsyncSession) -> List[ProfitSummary]:
        result = await db.execute(
            select(SaleItem, Product)
            .join(Product, SaleItem.product_id == Product.id, isouter=True)
        )
        rows = result.all()

        if not rows:
            return []

        data = []
        for sale_item, product in rows:
            if not product:
                continue
            data.append({
                "product_id":    product.id,
                "product_name":  product.name,
                "qty":           sale_item.quantity,
                "selling_price": sale_item.unit_price or product.selling_price,
                "cost_price":    product.cost_price,
            })

        df = pd.DataFrame(data)
        if df.empty:
            return []

        df["revenue"]     = df["qty"] * df["selling_price"]
        df["cost"]        = df["qty"] * df["cost_price"]
        df["gross_profit"] = df["revenue"] - df["cost"]

        summary = (
            df.groupby(["product_id", "product_name"])
            .agg(
                total_sold_qty=("qty", "sum"),
                total_revenue=("revenue", "sum"),
                total_cost=("cost", "sum"),
                gross_profit=("gross_profit", "sum"),
            )
            .reset_index()
        )

        # Create a dictionary for rapid unit lookup: product_id -> unit
        id_to_unit = {int(p.id): p.unit for _, p in rows if p}

        results = []
        for _, row in summary.iterrows():
            margin_pct = 0.0
            if row["total_cost"] > 0:
                margin_pct = round(row["gross_profit"] / row["total_cost"] * 100, 2)

            res_pid = int(row["product_id"])
            results.append(ProfitSummary(
                product_id=res_pid,
                product_name=row["product_name"],
                units_sold=round(row["total_sold_qty"], 3),
                total_revenue=round(row["total_revenue"], 2),
                total_cogs=round(row["total_cost"], 2),
                gross_profit=round(row["gross_profit"], 2),
                margin_pct=margin_pct,
                unit=id_to_unit.get(res_pid, "pcs")
            ))

        results.sort(key=lambda x: x.gross_profit, reverse=True)
        logger.info(f"Profit analysis complete: {len(results)} products")
        return results


# ═══════════════════════════════════════════════════════
# 2. DEMAND PREDICTION AGENT
# ═══════════════════════════════════════════════════════

class DemandPredictionAgent:
    """
    Forecasts short-term demand using:
      - Moving Average (last 7 days) for smoothed recent demand
      - Linear Regression (Scikit-Learn) for trend-based projection
    """

    MIN_DAYS_FOR_REGRESSION = 7

    async def run(self, db: AsyncSession) -> List[DemandForecast]:
        result = await db.execute(
            select(SaleItem, Sale, Product)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .join(Product, SaleItem.product_id == Product.id, isouter=True)
            .where(Product.id != None)  # noqa: E711
        )
        rows = result.all()

        if not rows:
            return []

        data = []
        for sale_item, sale, product in rows:
            data.append({
                "product_id":   product.id,
                "product_name": product.name,
                "qty":          sale_item.quantity,
                "current_stock": product.current_stock,
                "date":         sale.sale_date.date() if sale.sale_date else datetime.now().date(),
            })

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])

        forecasts = []
        for (product_id, product_name), group in df.groupby(["product_id", "product_name"]):
            daily = (
                group.groupby("date")["qty"]
                .sum()
                .reset_index()
                .sort_values("date")
            )

            full_range = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
            daily = daily.set_index("date").reindex(full_range, fill_value=0).reset_index()
            daily.columns = ["date", "qty"]

            avg_daily = float(daily["qty"].mean())
            n_days = len(daily)

            ma_7 = float(daily["qty"].tail(7).mean()) if n_days >= 3 else avg_daily

            if n_days >= self.MIN_DAYS_FOR_REGRESSION:
                X = np.arange(n_days).reshape(-1, 1)
                y = daily["qty"].values
                model = LinearRegression().fit(X, y)
                pred_7  = max(0, float(model.predict([[n_days + 6]])[0]))
                pred_30 = max(0, float(model.predict([[n_days + 29]])[0]))
                forecast_7d  = round((ma_7 * 0.5 + pred_7 * 0.5) * 7, 2)
                forecast_30d = round((avg_daily * 0.4 + pred_30 * 0.6) * 30, 2)
            else:
                forecast_7d  = round(ma_7 * 7, 2)
                forecast_30d = round(avg_daily * 30, 2)

            current_stock = group["current_stock"].iloc[-1]
            days_until_stockout = None
            stockout_risk = False

            if avg_daily > 0:
                days_until_stockout = round(current_stock / avg_daily, 1)
                stockout_risk = days_until_stockout <= 7

            # Get the unit for this product
            id_to_unit = {int(p.id): p.unit for _, _, p in rows if p}

            forecasts.append(DemandForecast(
                product_id=int(product_id),
                product_name=str(product_name),
                avg_daily_sales=round(avg_daily, 3),
                forecast_7d=forecast_7d,
                forecast_30d=forecast_30d,
                current_stock=round(current_stock, 2),
                stockout_risk=stockout_risk,
                days_until_stockout=days_until_stockout,
                unit=id_to_unit.get(int(product_id), "pcs")
            ))

        forecasts.sort(key=lambda x: (x.stockout_risk, -(x.days_until_stockout or 9999)))
        logger.info(f"Demand forecast complete: {len(forecasts)} products")
        return forecasts


# ═══════════════════════════════════════════════════════
# 3. RESTOCK RECOMMENDATION AGENT
# ═══════════════════════════════════════════════════════

class RestockRecommendationAgent:
    """
    Calculates optimal reorder quantity:
      Reorder Qty = (avg_daily_demand × lead_time_days) + safety_stock - current_stock

    Urgency levels: critical | soon | ok
    """

    async def run(
        self,
        db: AsyncSession,
        demand_forecasts: Optional[List[DemandForecast]] = None,
    ) -> List[RestockRecommendation]:

        result = await db.execute(
            select(Product).where(Product.is_active == True)  # noqa: E712
        )
        products = list(result.scalars().all())

        demand_map: Dict[int, float] = {}
        if demand_forecasts:
            demand_map = {f.product_id: f.avg_daily_sales for f in demand_forecasts}

        recommendations = []
        for product in products:
            avg_daily = demand_map.get(product.id, 0.0)
            effective_demand = max(avg_daily, 1.0)

            reorder_qty = (
                effective_demand * product.lead_time_days
                + product.safety_stock
                - product.current_stock
            )
            reorder_qty = max(0.0, round(reorder_qty, 2))

            if product.current_stock <= product.safety_stock:
                urgency = "critical"
                reason  = (
                    f"Stock ({product.current_stock:.1f}) is at or below "
                    f"safety stock ({product.safety_stock:.1f}). Order immediately."
                )
            elif product.current_stock <= product.reorder_point:
                urgency = "soon"
                reason  = (
                    f"Stock ({product.current_stock:.1f}) below reorder point "
                    f"({product.reorder_point:.1f}). Order within lead time "
                    f"({product.lead_time_days}d)."
                )
            else:
                urgency = "ok"
                reason  = (
                    f"Stock ({product.current_stock:.1f}) is adequate above "
                    f"reorder point ({product.reorder_point:.1f})."
                )

            recommendations.append(RestockRecommendation(
                product_id=product.id,
                product_name=product.name,
                current_stock=round(product.current_stock, 2),
                reorder_point=round(product.reorder_point, 2),
                reorder_quantity=reorder_qty,
                urgency=urgency,
                reason=reason,
                unit=product.unit
            ))

        order = {"critical": 0, "soon": 1, "ok": 2}
        recommendations.sort(key=lambda x: order[x.urgency])

        logger.info(
            f"Restock recs: "
            f"{sum(1 for r in recommendations if r.urgency=='critical')} critical, "
            f"{sum(1 for r in recommendations if r.urgency=='soon')} soon"
        )
        return recommendations


# ═══════════════════════════════════════════════════════
# 4. GST SUMMARY TOOL
# ═══════════════════════════════════════════════════════

class GSTSummaryTool:
    """
    Aggregates input GST (paid on supplier purchases) from InvoiceItems
    and produces monthly summaries.
    """

    async def run(
        self,
        db: AsyncSession,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> List[GSTSummary]:

        result = await db.execute(
            select(InvoiceItem, Invoice)
            .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
            .where(Invoice.status == "processed")
        )
        rows = result.all()

        if not rows:
            return []

        data = []
        for item, invoice in rows:
            created = invoice.created_at or datetime.now()
            data.append({
                "month":         created.strftime("%Y-%m"),
                "gst_amount":    item.gst_amount,
                "gst_rate":      item.gst_rate,
                "total_amount":  item.total_amount,
                "product":       item.raw_name,
                "invoice_id":    invoice.id,
            })

        df = pd.DataFrame(data)

        if year and month:
            target = f"{year:04d}-{month:02d}"
            df = df[df["month"] == target]

        if df.empty:
            return []

        summaries = []
        for month_str, group in df.groupby("month"):
            # Split "YYYY-MM"
            y_str, m_str = month_str.split("-")
            
            taxable = float(group["total_amount"].sum() - group["gst_amount"].sum())
            total_gst = float(group["gst_amount"].sum())
            
            # Simple assumption for simulation: 50/50 CGST/SGST if no IGST
            cgst = round(total_gst / 2, 2)
            sgst = round(total_gst / 2, 2)
            igst = 0.0

            breakdown_df = (
                group.groupby("gst_rate")["gst_amount"]
                .sum()
                .reset_index()
                .rename(columns={"gst_rate": "rate_pct", "gst_amount": "gst_collected"})
            )
            breakdown = breakdown_df.to_dict(orient="records")

            summaries.append(GSTSummary(
                year=int(y_str),
                month=int(m_str),
                taxable_amount=round(taxable, 2),
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total_gst=round(total_gst, 2),
                item_count=int(group["invoice_id"].nunique()),
                breakdown=breakdown,
            ))

        summaries.sort(key=lambda x: x.month, reverse=True)
        logger.info(f"GST summary: {len(summaries)} months processed")
        return summaries


# Singletons
profit_agent    = ProfitIntelligenceAgent()
demand_agent    = DemandPredictionAgent()
restock_agent   = RestockRecommendationAgent()
gst_tool        = GSTSummaryTool()
