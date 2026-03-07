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


class InvoiceConfirmOverride(BaseModel):
    id: int
    quantity: float
    unit_price: float
    profit_percentage: float = 20.0
    deleted: bool = False

class InvoiceConfirmRequest(BaseModel):
    overrides: Optional[List[InvoiceConfirmOverride]] = None


class ParsedItemDetail(OrmBase):
    id: Optional[int] = None
    raw_name: str
    inferred_name: Optional[str] = None
    quantity: float
    unit_price: float
    total_amount: float


class InvoiceProcessResponse(BaseModel):
    invoice_id:   int
    status:       str
    message:      str
    items_parsed: int = 0
    total_amount: float = 0.0
    total_gst:    float = 0.0
    parsed_item_details: List[ParsedItemDetail] = []


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
    id:                   int
    customer_id:          Optional[int]
    status:               str
    raw_text:             Optional[str]
    detected_language:    Optional[str]
    language_name:        Optional[str]
    language_probability: Optional[float]
    english_transcript:   Optional[str]
    amount_paid:          float
    total_amount:         float
    payment_status:       str
    sale_date:            Optional[datetime]
    created_at:           Optional[datetime]
    items:                List[SaleItemOut] = []


# ════════════════════════════════════════════════════════════
# Customer / Credit schemas
# ════════════════════════════════════════════════════════════

class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None


class CustomerOut(OrmBase):
    id: int
    name: str
    phone: Optional[str]
    total_credit: float
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class CreditTransactionOut(OrmBase):
    id: int
    customer_id: int
    sale_id: Optional[int]
    amount: float
    transaction_type: str
    created_at: Optional[datetime]


class ConfirmItemOverride(BaseModel):
    id: int
    quantity: float
    unit_price: float
    deleted: bool = False


class ConfirmSaleRequest(BaseModel):
    overrides: Optional[List[ConfirmItemOverride]] = None


class SaleProcessResponse(BaseModel):
    sale_id:              int
    status:               str
    message:              str
    transcript:           str                 # native-language transcript
    english_transcript:   str                 # English translation
    detected_language:    str                 # ISO 639-1 code
    language_name:        str                 # Human-readable name
    language_probability: float               # 0–1 confidence
    recording_prompt:     str                 # Suggested prompt for shopkeeper
    items_parsed:         int
    total_amount:         float
    customer_name:        Optional[str]       = None
    payment_status:       str                 = "paid"
    missing_products:     List[str]           = []
    needs_action:         bool                = False
    inventory_updated:    bool                = False
    credit_updated:       bool                = False
    parsed_item_details:  List[ParsedItemDetail] = []


class TextSaleRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=3,
        description="Natural language description, e.g. 'sold 2 kg rice and 5 soaps'",
    )
    language: Optional[str] = Field(
        None,
        description="Optional ISO 639-1 language hint (en/ta/ml/hi/kn). Auto-detected if omitted.",
    )
    amend_sale_id: Optional[int] = Field(
        None,
        description="Sale ID to amend if this is a correction to a pending sale",
    )


# ════════════════════════════════════════════════════════════
# Speech / Multilingual schemas
# ════════════════════════════════════════════════════════════

class MultilingualSpeechResponse(BaseModel):
    """Response from the dedicated speech detection endpoint."""
    detected_language:    str
    language_name:        str
    language_probability: float
    native_transcript:    str
    english_transcript:   str
    recording_prompt:     str


class SupportedLanguagesResponse(BaseModel):
    """List of supported languages with recording prompts."""
    languages:        Dict[str, str]   # {iso_code: language_name}
    recording_prompts: Dict[str, str]  # {iso_code: prompt_text}


# ════════════════════════════════════════════════════════════
# Analytics schemas
# ════════════════════════════════════════════════════════════

class ProfitSummary(BaseModel):
    product_id:     int
    product_name:   str
    units_sold:     float
    total_revenue:  float
    total_cogs:     float
    gross_profit:   float
    margin_pct:     float
    unit:           str


class DemandForecast(BaseModel):
    product_id:          int
    product_name:        str
    avg_daily_sales:     float
    forecast_7d:         float
    forecast_30d:        float
    current_stock:       float
    stockout_risk:       bool
    days_until_stockout: Optional[float]
    unit:                str


class RestockRecommendation(BaseModel):
    product_id:       int
    product_name:     str
    current_stock:    float
    reorder_point:    float
    reorder_quantity: float
    urgency:          str    # critical | soon | ok
    reason:           str
    unit:             str


class GSTBreakdownItem(BaseModel):
    rate_pct:      float
    gst_collected: float


class GSTSummary(BaseModel):
    year:            int
    month:           int
    taxable_amount:  float
    cgst:            float
    sgst:            float
    igst:            float
    total_gst:       float
    item_count:      int
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
