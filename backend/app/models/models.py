"""
ORM Models — SQLAlchemy async models for the AI CFO database.

Tables:
  products       — master product catalogue with stock & pricing
  invoices       — supplier invoice headers
  invoice_items  — line items from parsed invoices  → products
  sales          — customer sales sessions
  sale_items     — items per sale session            → products
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import relationship, Mapped

from app.db.database import Base


# ────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────

class InvoiceStatus(str, enum.Enum):
    PENDING               = "pending"
    PENDING_CONFIRMATION  = "pending_confirmation"
    PROCESSED             = "processed"
    FAILED                = "failed"


class SaleStatus(str, enum.Enum):
    PENDING   = "pending"
    PROCESSED = "processed"
    FAILED    = "failed"


class PaymentStatus(str, enum.Enum):
    PAID    = "paid"
    CREDIT  = "credit"
    PARTIAL = "partial"


class TransactionType(str, enum.Enum):
    CREDIT  = "credit"
    PAYMENT = "payment"


# ────────────────────────────────────────────────────────────
# Product — master catalogue
# ────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String(200), nullable=False, unique=True, index=True)
    sku            = Column(String(100), nullable=True, index=True)

    # Pricing
    cost_price     = Column(Float, default=0.0, nullable=False)
    selling_price  = Column(Float, default=0.0, nullable=False)
    gst_rate       = Column(Float, default=0.0)          # % e.g. 5.0 / 12.0 / 18.0

    # Stock management
    current_stock  = Column(Float, default=0.0, nullable=False)
    reorder_point  = Column(Float, default=5.0)          # trigger restock alert
    safety_stock   = Column(Float, default=2.0)          # minimum buffer
    lead_time_days = Column(Integer, default=3)          # supplier delivery days

    # Meta
    unit           = Column(String(20), default="pcs")   # kg / pcs / ltr …
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=func.now())
    updated_at     = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    invoice_items: Mapped[List["InvoiceItem"]] = relationship(
        "InvoiceItem", back_populates="product", lazy="select"
    )
    receipt_items: Mapped[List["ReceiptItem"]] = relationship(
        "ReceiptItem", back_populates="product", lazy="select"
    )
    sale_items: Mapped[List["SaleItem"]] = relationship(
        "SaleItem", back_populates="product", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r} stock={self.current_stock}>"


# ────────────────────────────────────────────────────────────
# Customer — ledger and credit tracking
# ────────────────────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String(200), nullable=False, index=True)
    phone          = Column(String(50), nullable=True)
    total_credit   = Column(Float, default=0.0, nullable=False)
    
    created_at     = Column(DateTime, default=func.now())
    updated_at     = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    sales: Mapped[List["Sale"]] = relationship("Sale", back_populates="customer", lazy="select")
    credit_transactions: Mapped[List["CreditTransaction"]] = relationship("CreditTransaction", back_populates="customer", lazy="select")

    def __repr__(self) -> str:
        return f"<Customer id={self.id} name={self.name!r} credit={self.total_credit}>"


# ────────────────────────────────────────────────────────────
# Invoice — supplier invoice header
# ────────────────────────────────────────────────────────────

class Invoice(Base):
    __tablename__ = "invoices"

    id             = Column(Integer, primary_key=True, index=True)
    file_path      = Column(String(500), nullable=True)
    status         = Column(Enum(InvoiceStatus), default=InvoiceStatus.PENDING, nullable=False)

    # Parsed header fields
    supplier_name  = Column(String(200), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    invoice_date   = Column(DateTime, nullable=True)

    # Aggregates
    total_amount   = Column(Float, default=0.0)
    total_gst      = Column(Float, default=0.0)

    # Raw content
    raw_ocr_text   = Column(Text, nullable=True)
    error_message  = Column(Text, nullable=True)

    # Meta
    created_at     = Column(DateTime, default=func.now())

    # Relationships
    items: Mapped[List["InvoiceItem"]] = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} supplier={self.supplier_name!r} status={self.status}>"


# ────────────────────────────────────────────────────────────
# InvoiceItem — one line from a supplier invoice
# ────────────────────────────────────────────────────────────

class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id           = Column(Integer, primary_key=True, index=True)
    invoice_id   = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=True)

    # As parsed from OCR
    raw_name     = Column(String(200), nullable=False)
    quantity     = Column(Float, nullable=False)
    unit_price   = Column(Float, nullable=False)
    gst_rate     = Column(Float, default=0.0)
    gst_amount   = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)

    # Relationships
    invoice: Mapped["Invoice"]      = relationship("Invoice", back_populates="items")
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="invoice_items")

    def __repr__(self) -> str:
        return f"<InvoiceItem id={self.id} name={self.raw_name!r} qty={self.quantity}>"


# ────────────────────────────────────────────────────────────
# Receipt — parsed customer receipt from OCR parser
# ────────────────────────────────────────────────────────────

class Receipt(Base):
    __tablename__ = "receipts"

    id              = Column(Integer, primary_key=True, index=True)
    file_path       = Column(String(500), nullable=True)

    # Parsed header fields from OCR parser.py output
    vendor_name     = Column(String(200), nullable=True)
    bill_number     = Column(String(100), nullable=True)
    receipt_date    = Column(DateTime, nullable=True)
    receipt_time    = Column(String(50), nullable=True)
    currency        = Column(String(10), default="INR")

    # Address and contact
    address         = Column(Text, nullable=True)
    phone           = Column(String(20), nullable=True)

    # Amounts
    subtotal        = Column(Float, default=0.0)
    tax             = Column(Float, default=0.0)
    discount        = Column(Float, default=0.0)
    total_amount    = Column(Float, default=0.0)

    # Payment info
    payment_method  = Column(String(50), nullable=True)

    # Raw content
    raw_ocr_text    = Column(Text, nullable=True)

    # Meta
    created_at      = Column(DateTime, default=func.now())

    # Relationships
    items: Mapped[List["ReceiptItem"]] = relationship(
        "ReceiptItem", back_populates="receipt", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Receipt id={self.id} vendor={self.vendor_name!r} total={self.total_amount}>"


# ────────────────────────────────────────────────────────────
# ReceiptItem — one line item from a parsed receipt
# ────────────────────────────────────────────────────────────

class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id            = Column(Integer, primary_key=True, index=True)
    receipt_id    = Column(Integer, ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    product_id    = Column(Integer, ForeignKey("products.id"), nullable=True)

    # As parsed from OCR
    item_name     = Column(String(200), nullable=False)
    quantity      = Column(Float, nullable=False)
    unit_price    = Column(Float, nullable=False)
    total_price   = Column(Float, nullable=False)

    # Relationships
    receipt: Mapped["Receipt"]      = relationship("Receipt", back_populates="items")
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="receipt_items")

    def __repr__(self) -> str:
        return f"<ReceiptItem id={self.id} name={self.item_name!r} qty={self.quantity}>"


# ────────────────────────────────────────────────────────────
# Sale — one customer sales session
# ────────────────────────────────────────────────────────────

class Sale(Base):
    __tablename__ = "sales"

    id             = Column(Integer, primary_key=True, index=True)
    customer_id    = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status         = Column(Enum(SaleStatus), default=SaleStatus.PENDING, nullable=False)

    # Payment / Credits
    amount_paid    = Column(Float, default=0.0)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PAID, nullable=False)

    # Input
    raw_audio_path        = Column(String(500), nullable=True)
    raw_text              = Column(Text, nullable=True)

    # Multilingual speech fields
    detected_language     = Column(String(10), nullable=True)   # ISO 639-1 code, e.g. "ta"
    language_name         = Column(String(50), nullable=True)   # e.g. "Tamil"
    language_probability  = Column(Float, nullable=True)        # Whisper detection confidence 0-1
    english_transcript    = Column(Text, nullable=True)         # EN translation of raw_text

    # Aggregate
    total_amount   = Column(Float, default=0.0)
    error_message  = Column(Text, nullable=True)

    # Meta
    sale_date      = Column(DateTime, default=func.now())
    created_at     = Column(DateTime, default=func.now())

    # Relationships
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="sales")
    items: Mapped[List["SaleItem"]] = relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan", lazy="select"
    )
    credit_transactions: Mapped[List["CreditTransaction"]] = relationship(
        "CreditTransaction", back_populates="sale", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Sale id={self.id} total={self.total_amount} status={self.status}>"


# ────────────────────────────────────────────────────────────
# SaleItem — one product in a sales session
# ────────────────────────────────────────────────────────────

class SaleItem(Base):
    __tablename__ = "sale_items"

    id           = Column(Integer, primary_key=True, index=True)
    sale_id      = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=True)

    # As parsed from voice/text
    raw_name     = Column(String(200), nullable=False)
    quantity     = Column(Float, nullable=False)
    unit_price   = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)

    # Relationships
    sale: Mapped["Sale"]                 = relationship("Sale", back_populates="items")
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="sale_items")

    def __repr__(self) -> str:
        return f"<SaleItem id={self.id} name={self.raw_name!r} qty={self.quantity}>"


# ────────────────────────────────────────────────────────────
# CreditTransaction — ledger entries for customers
# ────────────────────────────────────────────────────────────

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id               = Column(Integer, primary_key=True, index=True)
    customer_id      = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    sale_id          = Column(Integer, ForeignKey("sales.id"), nullable=True)
    amount           = Column(Float, nullable=False) # Positive value
    transaction_type = Column(Enum(TransactionType), nullable=False) # credit or payment
    
    created_at       = Column(DateTime, default=func.now())

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="credit_transactions")
    sale: Mapped[Optional["Sale"]] = relationship("Sale", back_populates="credit_transactions")

    def __repr__(self) -> str:
        return f"<CreditTransaction id={self.id} type={self.transaction_type} amount={self.amount}>"
