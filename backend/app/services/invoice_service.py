"""
Invoice Service
---------------
Orchestrates the full supplier invoice processing pipeline:

  Upload → OCR Agent → Invoice Parser → DB storage → Inventory update

Acts as the coordinator between agents.
"""

import os
import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from loguru import logger

from app.models.models import Invoice, InvoiceItem, InvoiceStatus, Product
from app.agents.ocr_agent import ocr_agent
from app.agents.invoice_parser import invoice_parser
from app.services.inventory_service import apply_purchase, find_product_by_name
from app.schemas.schemas import InvoiceProcessResponse, ParsedItemDetail
from app.core.config import settings


async def process_invoice_file(
    db: AsyncSession,
    file_path: str,
    original_filename: str,
) -> InvoiceProcessResponse:
    """
    Full pipeline: OCR → parse → persist → update inventory.
    Creates an Invoice record and InvoiceItems, then applies stock changes.
    """

    # 1. Create a PENDING invoice record
    invoice = Invoice(
        file_path=file_path,
        status=InvoiceStatus.PENDING,
    )
    db.add(invoice)
    await db.flush()   # get invoice.id
    logger.info(f"Invoice #{invoice.id} created for file: {original_filename}")

    try:
        # 2. Try FAST PATH (Groq Vision) — Sub-5 second extraction
        fast_parsed = await ocr_agent.try_fast_extraction(file_path)
        
        parsed = None
        if fast_parsed:
            try:
                # Convert the dict to a ParsedInvoice-like structure
                from app.agents.invoice_parser import ParsedInvoice, ParsedItem
                
                items = []
                for itm in fast_parsed.get("items", []):
                    # Robust field extraction with defaults
                    items.append(ParsedItem(
                        raw_name=str(itm.get("raw_name") or "Unknown Product"),
                        quantity=float(itm.get("quantity") or 0.0),
                        unit_price=float(itm.get("unit_price") or 0.0),
                        gst_rate=float(itm.get("gst_rate") or 0.0),
                        gst_amount=float(itm.get("gst_amount") or 0.0),
                        total_amount=float(itm.get("total_amount") or 0.0)
                    ))
                
                parsed = ParsedInvoice(
                    supplier_name=str(fast_parsed.get("supplier_name") or ""),
                    invoice_number=str(fast_parsed.get("invoice_number") or ""),
                    invoice_date=str(fast_parsed.get("invoice_date") or ""),
                    total_amount=float(fast_parsed.get("total_amount") or 0.0),
                    total_gst=float(fast_parsed.get("total_gst") or 0.0),
                    items=items
                )
            except Exception as e:
                logger.warning(f"Fast path parsing failed to map to schema: {e}. Falling back...")

        if not parsed:
            # 3. SLOW PATH (OCR -> LLM Parser) — Baseline behavior
            raw_text = await ocr_agent.run(file_path)
            
            if not raw_text.strip():
                raise ValueError("OCR returned no text. Check image quality.")

            invoice.raw_ocr_text = raw_text
            parsed = await invoice_parser.run(raw_text)

        if not parsed.items:
            raise ValueError("No line items could be parsed from the invoice.")

        # 4. Normalise Names (Shared)
        from app.agents.invoice_parser import invoice_parser
        parsed = await invoice_parser.normalize_parsed_invoice(parsed)
        
        # 5. Persist invoice header
        invoice.supplier_name   = parsed.supplier_name
        invoice.invoice_number  = parsed.invoice_number
        invoice.total_amount    = parsed.total_amount
        invoice.total_gst       = parsed.total_gst

        if parsed.invoice_date:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
                try:
                    invoice.invoice_date = datetime.strptime(parsed.invoice_date, fmt)
                    break
                except ValueError:
                    continue

        parsed_details = []
        
        # 5. Persist line items without updating inventory yet
        for parsed_item in parsed.items:
            db_item = InvoiceItem(
                invoice_id=invoice.id,
                raw_name=parsed_item.raw_name,
                quantity=parsed_item.quantity,
                unit_price=parsed_item.unit_price,
                gst_rate=parsed_item.gst_rate,
                gst_amount=parsed_item.gst_amount,
                total_amount=parsed_item.total_amount,
            )
            db.add(db_item)
            await db.flush()  # get db_item.id

            # Try to infer if it exists in DB for display purposes
            matched_product = await find_product_by_name(db, parsed_item.raw_name)
            
            parsed_details.append(
                ParsedItemDetail(
                    id=db_item.id,
                    raw_name=db_item.raw_name,
                    inferred_name=matched_product.name if matched_product else None,
                    quantity=float(db_item.quantity),
                    unit_price=float(db_item.unit_price),
                    total_amount=float(db_item.total_amount),
                )
            )

        invoice.status = InvoiceStatus.PENDING_CONFIRMATION
        logger.info(
            f"Invoice #{invoice.id} requires confirmation: "
            f"{len(parsed.items)} items, total={parsed.total_amount:.2f}"
        )

        return InvoiceProcessResponse(
            invoice_id=invoice.id,
            status="pending_confirmation",
            message=f"Please confirm or edit the {len(parsed.items)} parsed line items.",
            items_parsed=len(parsed.items),
            total_amount=parsed.total_amount,
            total_gst=parsed.total_gst,
            parsed_item_details=parsed_details
        )

    except Exception as e:
        logger.error(f"Invoice #{invoice.id} processing failed: {e}")
        invoice.status = InvoiceStatus.FAILED
        invoice.error_message = str(e)

        return InvoiceProcessResponse(
            invoice_id=invoice.id,
            status="failed",
            message=f"Processing failed: {e}",
            items_parsed=0,
            total_amount=0.0,
            total_gst=0.0,
        )


async def get_invoice(db: AsyncSession, invoice_id: int) -> Optional[Invoice]:
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice_id)
    )
    return result.scalar_one_or_none()


async def get_all_invoices(db: AsyncSession) -> list:
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .order_by(Invoice.created_at.desc())
    )
    return list(result.scalars().all())

async def confirm_invoice_items(
    db: AsyncSession, 
    invoice_id: int, 
    overrides_data: Optional[list]
) -> InvoiceProcessResponse:
    """
    Finalizes the invoice. Applies user overrides (quantity, cost_price, profit) 
    and then commits the line items to inventory.
    """
    invoice = await get_invoice(db, invoice_id)
    if not invoice:
        raise ValueError("Invoice not found")
        
    if invoice.status != InvoiceStatus.PENDING_CONFIRMATION:
        raise ValueError(f"Invoice is {invoice.status.value}, cannot confirm")
        
    # Map overrides by item_id
    overrides_map = {}
    if overrides_data:
        for idx, ov in enumerate(overrides_data):
            # ov might be a Pydantic model or a dict depending on FastAPI behavior
            try:
                ov_id = ov.id if hasattr(ov, 'id') else ov.get("id")
            except:
                ov_id = None
                
            cid = ov_id if ov_id is not None else idx 
            overrides_map[cid] = ov
            logger.debug(f"Mapped override for item {cid}: {ov}")

    active_items = []
    
    # Process line items
    for item in invoice.items:
        override = overrides_map.get(item.id)
        
        if override:
            is_deleted = override.deleted if hasattr(override, 'deleted') else override.get("deleted", False)
            if is_deleted:
                # User deleted this item from the confirmation screen
                logger.info(f"Deleting item {item.id} per user override")
                await db.delete(item)
                continue
                
            item.quantity = override.quantity if hasattr(override, 'quantity') else override.get("quantity", item.quantity)
            item.unit_price = override.unit_price if hasattr(override, 'unit_price') else override.get("unit_price", item.unit_price)
            item.total_amount = round(item.quantity * item.unit_price, 2)
            profit_pct = override.profit_percentage if hasattr(override, 'profit_percentage') else override.get("profit_percentage", 20.0)
        else:
            profit_pct = 20.0
            
        active_items.append(item)
        
        # Apply stock update + set custom selling price
        await apply_purchase(
            db, 
            item, 
            custom_profit_margin=profit_pct
        )

    # Recalculate totals
    invoice.total_amount = sum(i.total_amount for i in active_items)
    invoice.status = InvoiceStatus.PROCESSED
    
    await db.flush()

    return InvoiceProcessResponse(
        invoice_id=invoice.id,
        status="processed",
        message="Invoice confirmed and inventory updated successfully.",
        items_parsed=len(active_items),
        total_amount=invoice.total_amount,
        total_gst=invoice.total_gst if invoice.total_gst is not None else 0.0
    )
