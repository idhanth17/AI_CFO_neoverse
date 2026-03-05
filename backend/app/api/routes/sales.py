"""
Sales Routes — /api/sales
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.config import settings
from app.db.database import get_db
from app.schemas.schemas import SaleOut, SaleProcessResponse, TextSaleRequest
from app.services.sales_service import (
    process_voice_sale, process_text_sale, get_sale, get_all_sales
)

router = APIRouter(prefix="/api/sales", tags=["Sales"])

ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg",
    "audio/webm", "audio/x-wav", "audio/wave",
}


@router.post("/voice", response_model=SaleProcessResponse, status_code=status.HTTP_201_CREATED)
async def record_voice_sale(
    file: UploadFile = File(..., description="Audio recording of the shopkeeper describing sales"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a voice recording. Runs: Whisper transcription → sales parse → inventory deduction.
    """
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type: {file.content_type}",
        )

    ext = Path(file.filename or "audio").suffix or ".wav"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_dir = Path(settings.UPLOAD_DIR) / "audio"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / unique_name

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds {settings.MAX_UPLOAD_MB} MB limit.",
        )

    with open(save_path, "wb") as f:
        f.write(contents)

    logger.info(f"Audio saved: {save_path}")
    return await process_voice_sale(db, str(save_path))


@router.post("/text", response_model=SaleProcessResponse, status_code=status.HTTP_201_CREATED)
async def record_text_sale(
    payload: TextSaleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a manual text description, e.g. 'sold 2 kg rice and 5 soaps'.
    Runs: parse → inventory deduction.
    """
    return await process_text_sale(db, payload.text)


@router.get("/", response_model=list[SaleOut])
async def list_sales(db: AsyncSession = Depends(get_db)):
    """List all sales sessions (newest first)."""
    return await get_all_sales(db)


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale_detail(sale_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single sale with all its line items."""
    sale = await get_sale(db, sale_id)
    if not sale:
        raise HTTPException(status_code=404, detail=f"Sale #{sale_id} not found")
    return sale
