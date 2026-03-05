"""
Sales Service
-------------
Orchestrates the customer sales pipeline:

  Voice Upload → Whisper → Sales Parser → DB storage → Inventory reduction
  Manual Text  →          Sales Parser → DB storage → Inventory reduction
"""

import os
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models.models import Sale, SaleItem, SaleStatus
from app.agents.speech_agent import speech_agent
from app.agents.sales_parser import sales_parser
from app.services.inventory_service import apply_sale
from app.schemas.schemas import SaleProcessResponse


async def process_voice_sale(
    db: AsyncSession,
    audio_path: str,
) -> SaleProcessResponse:
    """Pipeline: transcribe audio → parse → persist → deduct stock."""
    sale = Sale(raw_audio_path=audio_path, status=SaleStatus.PENDING)
    db.add(sale)
    await db.flush()
    logger.info(f"Sale #{sale.id} created from audio: {audio_path}")

    try:
        transcript = speech_agent.transcribe_file(audio_path)
        if not transcript.strip():
            raise ValueError("Transcription returned empty text. Speak clearly near the microphone.")

        sale.raw_text = transcript
        return await _process_sale_text(db, sale, transcript)

    except Exception as e:
        logger.error(f"Voice sale #{sale.id} failed: {e}")
        sale.status = SaleStatus.FAILED
        sale.error_message = str(e)
        return SaleProcessResponse(
            sale_id=sale.id, status="failed",
            message=str(e), transcript="",
            items_parsed=0, total_amount=0.0,
        )


async def process_text_sale(
    db: AsyncSession,
    text: str,
) -> SaleProcessResponse:
    """Pipeline (manual text fallback): parse text → persist → deduct stock."""
    sale = Sale(raw_text=text, status=SaleStatus.PENDING)
    db.add(sale)
    await db.flush()
    logger.info(f"Sale #{sale.id} created from manual text")

    try:
        return await _process_sale_text(db, sale, text)
    except Exception as e:
        logger.error(f"Text sale #{sale.id} failed: {e}")
        sale.status = SaleStatus.FAILED
        sale.error_message = str(e)
        return SaleProcessResponse(
            sale_id=sale.id, status="failed",
            message=str(e), transcript=text,
            items_parsed=0, total_amount=0.0,
        )


async def _process_sale_text(
    db: AsyncSession,
    sale: Sale,
    text: str,
) -> SaleProcessResponse:
    """Shared logic: parse text → create SaleItems → update inventory."""

    parsed = sales_parser.run(text)

    if not parsed.items:
        raise ValueError(
            f"Could not extract any sale items from: '{text}'. "
            "Try: 'sold 2 kg rice and 5 soaps'"
        )

    total_amount = 0.0

    for parsed_item in parsed.items:
        db_item = SaleItem(
            sale_id=sale.id,
            raw_name=parsed_item.raw_name,
            quantity=parsed_item.quantity,
        )
        db.add(db_item)
        await db.flush()

        await apply_sale(db, db_item)
        total_amount += db_item.total_amount

    sale.total_amount = round(total_amount, 2)
    sale.status = SaleStatus.PROCESSED

    logger.info(
        f"Sale #{sale.id} processed: {len(parsed.items)} items, "
        f"total={total_amount:.2f}"
    )

    return SaleProcessResponse(
        sale_id=sale.id,
        status="processed",
        message=f"Sale recorded with {len(parsed.items)} item(s).",
        transcript=text,
        items_parsed=len(parsed.items),
        total_amount=round(total_amount, 2),
    )


async def get_sale(db: AsyncSession, sale_id: int) -> Optional[Sale]:
    result = await db.execute(select(Sale).where(Sale.id == sale_id))
    return result.scalar_one_or_none()


async def get_all_sales(db: AsyncSession) -> list:
    result = await db.execute(select(Sale).order_by(Sale.created_at.desc()))
    return list(result.scalars().all())
