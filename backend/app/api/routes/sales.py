"""
Sales Routes — /api/sales
"""

import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
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
    file: UploadFile = File(
        ...,
        description=(
            "Audio recording of the shopkeeper describing sales. "
            "Supported languages: English, Tamil, Malayalam, Hindi, Kannada. "
            "Language is auto-detected — no configuration needed."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    amend_sale_id: Optional[int] = Form(None),
):
    """
    Upload a voice recording in any supported language.

    Pipeline:
      Audio → Whisper language detection → Native transcription
           → English translation → Sales Parser → Inventory deduction

    The response includes both the native transcript and the English
    translation, along with the detected language and confidence.
    """
    base_media_type = file.content_type.split(";")[0].strip()
    if base_media_type not in ALLOWED_AUDIO_TYPES and not base_media_type.startswith("audio/"):
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

    logger.info(f"Audio saved temporarily: {save_path}")
    
    try:
        if amend_sale_id:
            from app.services.sales_service import amend_sale_voice
            return await amend_sale_voice(db, str(save_path), amend_sale_id)
        return await process_voice_sale(db, str(save_path))
    finally:
        # Cleanup audio file after processing so we don't store them
        try:
            if save_path.exists():
                save_path.unlink()
                logger.info(f"Temporary audio deleted: {save_path}")
        except Exception as e:
            logger.error(f"Failed to delete temp audio {save_path}: {e}")


@router.post("/text", response_model=SaleProcessResponse, status_code=status.HTTP_201_CREATED)
async def record_text_sale(
    payload: TextSaleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a manual text description.

    Examples:
      - English: \"sold 2 kg rice and 5 soaps\"
      - Tamil:   (pre-translated English text)

    Optionally provide `language` (ISO 639-1 code: en / ta / ml / hi / kn)
    to tag the entry.  The Sales Parser always runs on the provided text,
    so please send English for best results.
    """
    if payload.amend_sale_id:
        from app.services.sales_service import amend_sale_text
        return await amend_sale_text(db, payload.text, payload.amend_sale_id, language=payload.language)
    return await process_text_sale(db, payload.text, language=payload.language)


@router.post("/{sale_id}/confirm", response_model=SaleProcessResponse, status_code=status.HTTP_200_OK)
async def confirm_sale(sale_id: int, db: AsyncSession = Depends(get_db)):
    """Confirm a pending sale, deducting inventory and updating credit."""
    from app.services.sales_service import confirm_sale_action
    sale = await get_sale(db, sale_id)
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    try:
        return await confirm_sale_action(db, sale)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.get("/", response_model=List[SaleOut])
async def list_sales(db: AsyncSession = Depends(get_db)):
    """List all sales sessions (newest first), including language metadata."""
    return await get_all_sales(db)


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale_detail(sale_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single sale with all its line items and language metadata."""
    sale = await get_sale(db, sale_id)
    if not sale:
        raise HTTPException(status_code=404, detail=f"Sale #{sale_id} not found")
    return sale
