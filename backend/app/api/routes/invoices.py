"""
Invoice Routes — /api/invoices
"""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.config import settings
from app.db.database import get_db
from app.models.models import Invoice, InvoiceItem
from app.schemas.schemas import InvoiceOut, InvoiceItemOut, InvoiceProcessResponse
from app.services.invoice_service import (
    process_invoice_file, get_invoice, get_all_invoices
)

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])

ALLOWED_TYPES = {
    "image/png", "image/jpeg", "image/tiff",
    "image/bmp", "image/webp", "application/pdf",
}
MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


@router.post("/upload", response_model=InvoiceProcessResponse, status_code=status.HTTP_201_CREATED)
async def upload_invoice(
    file: UploadFile = File(..., description="Supplier invoice image or PDF"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a supplier invoice (PNG / JPG / PDF).
    Runs the full pipeline: OCR → parse → inventory update.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    # Save to disk
    ext = Path(file.filename or "invoice").suffix or ".png"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_dir = Path(settings.UPLOAD_DIR) / "invoices"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / unique_name

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_MB} MB.",
        )

    with open(save_path, "wb") as f:
        f.write(contents)

    logger.info(f"Invoice file saved: {save_path}")
    return await process_invoice_file(db, str(save_path), file.filename or unique_name)


@router.get("/", response_model=list[InvoiceOut])
async def list_invoices(db: AsyncSession = Depends(get_db)):
    """List all invoices (newest first)."""
    invoices = await get_all_invoices(db)
    return invoices


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice_detail(invoice_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single invoice with all its line items."""
    invoice = await get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice #{invoice_id} not found")
    return invoice
