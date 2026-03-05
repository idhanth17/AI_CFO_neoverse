"""
Invoice Service
---------------
Orchestrates the full supplier invoice processing pipeline:

  Upload → OCR Agent → Invoice Parser → DB storage → Inventory update

Acts as the coordinator between agents.
"""

import os
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models.models import Invoice, InvoiceItem, InvoiceStatus
from app.agents.ocr_agent import ocr_agent
from app.agents.invoice_parser import invoice_parser
from app.services.inventory_service import apply_purchase
from app.schemas.schemas import InvoiceProcessResponse
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
        # 2. OCR — extract raw text
        raw_text = ocr_agent.run(file_path)

        if not raw_text.strip():
            raise ValueError("OCR returned no text. Check image quality.")

        invoice.raw_ocr_text = raw_text

        # 3. Parse — convert OCR text to structured data
        parsed = invoice_parser.run(raw_text)

        if not parsed.items:
            raise ValueError("No line items could be parsed from the invoice.")

        # 4. Persist invoice header
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

        # 5. Persist line items + update inventory
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

            await apply_purchase(db, db_item)

        invoice.status = InvoiceStatus.PROCESSED
        logger.info(
            f"Invoice #{invoice.id} processed successfully: "
            f"{len(parsed.items)} items, total={parsed.total_amount:.2f}"
        )

        return InvoiceProcessResponse(
            invoice_id=invoice.id,
            status="processed",
            message=f"Invoice processed successfully with {len(parsed.items)} line items.",
            items_parsed=len(parsed.items),
            total_amount=parsed.total_amount,
            total_gst=parsed.total_gst,
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
        select(Invoice).where(Invoice.id == invoice_id)
    )
    return result.scalar_one_or_none()


async def get_all_invoices(db: AsyncSession) -> list:
    result = await db.execute(
        select(Invoice).order_by(Invoice.created_at.desc())
    )
    return list(result.scalars().all())
