"""
Pydantic Schemas — Request and Response models for all API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ════════════════════════════════════════════════════════════
# Shared base
# ════════════════════════════════════════════════════════════

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════
# Product schemas
# ════════════════════════════════════════════════════════════

class ProductCreate(BaseModel):
    name:           str   = Field(..., min_length=1, max_length=200)
    sku:            Optional[str] = None
    cost_price:     float = Field(0.0, ge=0)
    selling_price:  float = Field(0.0, ge=0)
    gst_rate:       float = Field(0.0, ge=0, le=100)
    current_stock:  float = Field(0.0, ge=0)
    reorder_point:  float = Field(5.0, ge=0)
    safety_stock:   float = Field(2.0, ge=0)
    lead_time_days: int   = Field(3, ge=0)
    unit:           str   = "pcs"


class ProductUpdate(BaseModel):
    """All fields optional — PATCH-style update."""
    sku:            Optional[str]   = None
    cost_price:     Optional[float] = None
    selling_price:  Optional[float] = None
    gst_rate:       Optional[float] = None
    current_stock:  Optional[float] = None
    reorder_point:  Optional[float] = None
    safety_stock:   Optional[float] = None
    lead_time_days: Optional[int]   = None
    unit:           Optional[str]   = None
    is_active:      Optional[bool]  = None


class ProductOut(OrmBase):
    id:             int
    name:           str
    sku:            Optional[str]
    cost_price:     float
    selling_price:  float
    gst_rate:       float
    current_stock:  float
    reorder_point:  float
    safety_stock:   float
    lead_time_days: int
    unit:           str
    is_active:      bool
    created_at:     Optional[datetime]
    updated_at:     Optional[datetime]


# ════════════════════════════════════════════════════════════
# Invoice schemas
# ════════════════════════════════════════════════════════════

class InvoiceItemOut(OrmBase):
    id:           int
    raw_name:     str
    quantity:     float
    unit_price:   float
    gst_rate:     float
    gst_amount:   float
    total_amount: float
    product_id:   Optional[int]


class InvoiceOut(OrmBase):
    id:             int
    status:         str
    supplier_name:  Optional[str]
    invoice_number: Optional[str]
    invoice_date:   Optional[datetime]
    total_amount:   float
    total_gst:      float
    file_path:      Optional[str]
    created_at:     Optional[datetime]
    items:          List[InvoiceItemOut] = []


class InvoiceProcessResponse(BaseModel):
    invoice_id:   int
    status:       str
    message:      str
    items_parsed: int
    total_amount: float
    total_gst:    float


# ════════════════════════════════════════════════════════════
# Sales schemas
# ════════════════════════════════════════════════════════════

class SaleItemOut(OrmBase):
    id:           int
    raw_name:     str
    quantity:     float
    unit_price:   float
    total_amount: float
    product_id:   Optional[int]


class SaleOut(OrmBase):
    id:           int
    status:       str
    raw_text:     Optional[str]
    total_amount: float
    sale_date:    Optional[datetime]
    created_at:   Optional[datetime]
    items:        List[SaleItemOut] = []


class SaleProcessResponse(BaseModel):
    sale_id:      int
    status:       str
    message:      str
    transcript:   str
    items_parsed: int
    total_amount: float


class TextSaleRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=3,
        description="Natural language description, e.g. 'sold 2 kg rice and 5 soaps'",
    )


# ════════════════════════════════════════════════════════════
# Analytics schemas
# ════════════════════════════════════════════════════════════

class ProfitSummary(BaseModel):
    product_id:     int
    product_name:   str
    total_sold_qty: float
    total_revenue:  float
    total_cost:     float
    gross_profit:   float
    margin_pct:     float


class DemandForecast(BaseModel):
    product_id:          int
    product_name:        str
    avg_daily_demand:    float
    forecast_7d:         float
    forecast_30d:        float
    current_stock:       float
    stockout_risk:       bool
    days_until_stockout: Optional[float]


class RestockRecommendation(BaseModel):
    product_id:      int
    product_name:    str
    current_stock:   float
    reorder_point:   float
    recommended_qty: float
    urgency:         str    # critical | soon | ok
    reason:          str


class GSTBreakdownItem(BaseModel):
    rate_pct:      float
    gst_collected: float


class GSTSummary(BaseModel):
    month:           str     # "YYYY-MM"
    total_purchases: float
    total_gst_paid:  float
    invoice_count:   int
    breakdown:       List[Dict[str, Any]] = []


class DashboardResponse(BaseModel):
    """Aggregated response for the main dashboard."""
    total_products:      int
    low_stock_count:     int
    total_invoices:      int
    total_sales:         int
    total_revenue:       float
    total_purchases:     float
    profit_summary:      List[ProfitSummary]
    demand_forecasts:    List[DemandForecast]
    restock_recs:        List[RestockRecommendation]
    gst_summary:         List[GSTSummary]
