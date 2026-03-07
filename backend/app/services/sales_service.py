"""
Sales Service
-------------
Orchestrates the customer sales pipeline:

  Voice Upload → Whisper (multilingual) → English text → Sales Parser → DB storage → Inventory reduction
  Manual Text  →                          Sales Parser → DB storage → Inventory reduction

Multilingual support:
  • Auto-detects spoken language (EN / Tamil / Malayalam / Hindi / Kannada).
  • Stores the native-language transcript in Sale.raw_text.
  • Stores the English translation in Sale.english_transcript.
  • The Sales Parser always runs on the English text.
"""

import os
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from loguru import logger

from app.models.models import Sale, SaleItem, SaleStatus, Customer, CreditTransaction, PaymentStatus, TransactionType
from app.agents.speech_agent import speech_agent, RECORDING_PROMPTS, SUPPORTED_LANGUAGES
from app.agents.sales_parser import sales_parser
from app.services.inventory_service import apply_sale
from app.schemas.schemas import SaleProcessResponse, ParsedItemDetail


# ─────────────────────────────────────────────────────────────────────────────
# Voice sale pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def process_voice_sale(
    db: AsyncSession,
    audio_path: str,
) -> SaleProcessResponse:
    """Pipeline: transcribe audio (multilingual) → parse → persist → deduct stock."""
    sale = Sale(raw_audio_path=audio_path, status=SaleStatus.PENDING)
    db.add(sale)
    await db.flush()
    logger.info(f"Sale #{sale.id} created from audio: {audio_path}")

    try:
        # ── Multilingual transcription ────────────────────────────────────────
        speech_result = speech_agent.transcribe_file(audio_path)

        native_text   = speech_result.native_transcript
        english_text  = speech_result.english_transcript

        if not native_text.strip():
            raise ValueError(
                "Transcription returned empty text. "
                "Please speak clearly near the microphone."
            )

        # ── Persist speech metadata on the sale row ───────────────────────────
        sale.raw_text             = native_text
        sale.english_transcript   = english_text
        sale.detected_language    = speech_result.detected_language
        sale.language_name        = speech_result.language_name
        sale.language_probability = speech_result.language_probability

        logger.info(
            f"Sale #{sale.id} — language: {speech_result.language_name} "
            f"({speech_result.detected_language}), "
            f"confidence: {speech_result.language_probability:.1%}"
        )

        # ── Parse & inventory ─────────────────────────────────────────────────
        return await _process_sale_text(
            db, sale,
            parse_text     = english_text,
            display_transcript = native_text,
            speech_result  = speech_result,
        )

    except Exception as exc:
        logger.error(f"Voice sale #{sale.id} failed: {exc}")
        sale.status = SaleStatus.FAILED
        sale.error_message = str(exc)
        # Use language data already captured on the sale (if speech ran ok)
        lang_code  = sale.detected_language    or "en"
        lang_name  = sale.language_name        or "English"
        lang_prob  = sale.language_probability or 0.0
        eng_text   = sale.english_transcript   or ""
        nat_text   = sale.raw_text             or ""
        rec_prompt = RECORDING_PROMPTS.get(lang_code, RECORDING_PROMPTS["en"])
        return SaleProcessResponse(
            sale_id=sale.id,
            status="failed",
            message=str(exc),
            transcript=nat_text,
            english_transcript=eng_text,
            detected_language=lang_code,
            language_name=lang_name,
            language_probability=lang_prob,
            recording_prompt=rec_prompt,
            items_parsed=0,
            total_amount=0.0,
            customer_name=None,
            payment_status="paid",
            missing_products=[],
            needs_action=False,
            inventory_updated=False,
            credit_updated=False,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Text sale pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def process_text_sale(
    db: AsyncSession,
    text: str,
    language: Optional[str] = None,
) -> SaleProcessResponse:
    """
    Pipeline (manual text input):
      Text (any supported language) → parse → persist → deduct stock.

    If the caller knows the language, pass the ISO 639-1 code so it can be
    stored.  The Sales Parser always runs on the text as-is (assumed English
    or pre-translated by the caller).
    """
    sale = Sale(raw_text=text, status=SaleStatus.PENDING)

    # Store language hint if provided
    if language and language in SUPPORTED_LANGUAGES:
        sale.detected_language    = language
        sale.language_name        = SUPPORTED_LANGUAGES[language]
        sale.language_probability = 1.0   # explicitly set → 100 % confident
        sale.english_transcript   = text  # caller is responsible for sending EN text
    else:
        sale.detected_language    = "en"
        sale.language_name        = "English"
        sale.language_probability = 1.0
        sale.english_transcript   = text

    db.add(sale)
    await db.flush()
    logger.info(f"Sale #{sale.id} created from manual text (lang={sale.detected_language})")

    try:
        return await _process_sale_text(
            db, sale,
            parse_text         = text,
            display_transcript = text,
            speech_result      = None,
        )
    except Exception as exc:
        logger.error(f"Text sale #{sale.id} failed: {exc}")
        sale.status = SaleStatus.FAILED
        sale.error_message = str(exc)
        return SaleProcessResponse(
            sale_id=sale.id,
            status="failed",
            message=str(exc),
            transcript=text,
            english_transcript=text,
            detected_language=sale.detected_language or "en",
            language_name=sale.language_name or "English",
            language_probability=sale.language_probability or 1.0,
            recording_prompt=RECORDING_PROMPTS.get(sale.detected_language or "en",
                                                    RECORDING_PROMPTS["en"]),
            items_parsed=0,
            total_amount=0.0,
            customer_name=None,
            payment_status="paid",
            missing_products=[],
            needs_action=False,
            inventory_updated=False,
            credit_updated=False,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Shared parsing + inventory logic
# ─────────────────────────────────────────────────────────────────────────────

async def amend_sale_voice(db: AsyncSession, audio_path: str, amend_sale_id: int) -> SaleProcessResponse:
    sale = await get_sale(db, amend_sale_id)
    if not sale or sale.status != SaleStatus.PENDING:
        raise ValueError("Cannot amend this sale (not found or already processed)")
    
    speech_result = speech_agent.transcribe_file(audio_path)
    existing_eng = sale.english_transcript
    
    sale.raw_audio_path = audio_path
    sale.raw_text = speech_result.native_transcript
    sale.english_transcript = speech_result.english_transcript
    sale.detected_language = speech_result.detected_language
    sale.language_name = speech_result.language_name
    sale.language_probability = speech_result.language_probability

    logger.info(f"Amending Sale #{sale.id} via voice")

    for itm in sale.items:
        await db.delete(itm)
    sale.items.clear()
    await db.flush()

    return await _process_sale_text(
        db, sale,
        parse_text=speech_result.english_transcript,
        display_transcript=speech_result.native_transcript,
        speech_result=speech_result,
        amend_context=existing_eng
    )

async def amend_sale_text(db: AsyncSession, text: str, amend_sale_id: int, language: Optional[str] = None) -> SaleProcessResponse:
    sale = await get_sale(db, amend_sale_id)
    if not sale or sale.status != SaleStatus.PENDING:
        raise ValueError("Cannot amend this sale (not found or already processed)")
        
    existing_eng = sale.english_transcript
    sale.raw_text = text
    sale.english_transcript = text
    
    if language and language in SUPPORTED_LANGUAGES:
        sale.detected_language = language
        sale.language_name = SUPPORTED_LANGUAGES[language]
    else:
        sale.detected_language = "en"
        sale.language_name = "English"
    
    logger.info(f"Amending Sale #{sale.id} via text")
    
    for itm in sale.items:
        await db.delete(itm)
    sale.items.clear()
    await db.flush()

    return await _process_sale_text(
        db, sale,
        parse_text=text,
        display_transcript=text,
        speech_result=None,
        amend_context=existing_eng
    )

async def _process_sale_text(
    db: AsyncSession,
    sale: Sale,
    parse_text: str,
    display_transcript: str,
    speech_result,          # SpeechResult | None
    amend_context: str = None,
) -> SaleProcessResponse:
    """Shared logic: parse English text → create SaleItems → prepare Sale"""

    parsed = sales_parser.run(parse_text, existing_context=amend_context)

    if not parsed.items:
        raise ValueError(
            f"Could not extract any sale items from the transcript. "
            f"Try speaking: 'Sold 2 kg rice and 5 soaps' (in any supported language)."
        )

    # ── Pre-check inventory with AI Fuzzy Logic ──
    from app.services.inventory_service import find_product_by_name
    from sqlalchemy.future import select
    from app.models.models import Product
    import difflib

    missing_products = []
    
    # Pre-fetch catalog names for fast fuzzy matching
    res = await db.execute(select(Product))
    all_products = res.scalars().all()
    all_product_names = [p.name for p in all_products]
    
    for parsed_item in parsed.items:
        # 1. Exact or ilike match first
        prod = next((p for p in all_products if p.name.lower() == parsed_item.raw_name.lower()), None)
        
        if not prod:
            # 2. Fuzzy match closely
            matches = difflib.get_close_matches(parsed_item.raw_name, all_product_names, n=1, cutoff=0.3)
            if matches:
                logger.info(f"AI Auto-correction: '{parsed_item.raw_name}' -> '{matches[0]}'")
                parsed_item.raw_name = matches[0]
            else:
                missing_products.append(parsed_item.raw_name)

    if missing_products:
        sale.status = SaleStatus.FAILED
        sale.error_message = f"Products not in inventory: {', '.join(missing_products)}"
        logger.warning(f"Sale #{sale.id} paused - Missing products: {missing_products}")
        
        # Build response with action required flag
        lang_code    = sale.detected_language    or "en"
        lang_name    = sale.language_name        or "English"
        lang_prob    = sale.language_probability or 1.0
        eng_text     = sale.english_transcript   or display_transcript
        rec_prompt   = (
            speech_result.recording_prompt
            if speech_result else
            RECORDING_PROMPTS.get(lang_code, RECORDING_PROMPTS["en"])
        )
        return SaleProcessResponse(
            sale_id              = sale.id,
            status               = "needs_action",
            message              = f"Missing inventory items: {', '.join(missing_products)}. Please add them first.",
            transcript           = display_transcript,
            english_transcript   = eng_text,
            detected_language    = lang_code,
            language_name        = lang_name,
            language_probability = round(lang_prob, 4),
            recording_prompt     = rec_prompt,
            items_parsed         = len(parsed.items),
            total_amount         = 0.0,
            customer_name        = parsed.customer_name,
            payment_status       = parsed.payment_status,
            missing_products     = missing_products,
            needs_action         = True,
            inventory_updated    = False,
            credit_updated       = False,
        )

    total_amount = 0.0
    parsed_item_details = []

    for parsed_item in parsed.items:
        prod = next((p for p in all_products if p.name == parsed_item.raw_name), None)
        unit_price = prod.selling_price if prod else 0.0
        item_total = round(unit_price * parsed_item.quantity, 2)
        
        db_item = SaleItem(
            sale_id      = sale.id,
            product_id   = prod.id if prod else None,
            raw_name     = parsed_item.raw_name,
            quantity     = parsed_item.quantity,
            unit_price   = unit_price,
            total_amount = item_total,
        )
        db.add(db_item)
        await db.flush()
        # DEFERRED to confirm step: await apply_sale(db, db_item)
        total_amount += item_total
        
        parsed_item_details.append(ParsedItemDetail(
            raw_name=parsed_item.raw_name,
            inferred_name=prod.name if prod else None,
            quantity=parsed_item.quantity,
            unit_price=unit_price,
            total_amount=item_total
        ))

    sale.total_amount = round(total_amount, 2)
    sale.status       = SaleStatus.PENDING
    
    # Map parsed status to Enum
    pay_status_lower = parsed.payment_status.lower()
    if pay_status_lower == "credit":
        sale.payment_status = PaymentStatus.CREDIT
        sale.amount_paid = 0.0
    elif pay_status_lower == "partial":
        sale.payment_status = PaymentStatus.PARTIAL
        sale.amount_paid = round(total_amount / 2, 2) # default 50% for partial if not specified
    else:
        sale.payment_status = PaymentStatus.PAID
        sale.amount_paid = sale.total_amount

    # ── Handle Customer (Preview) ──
    cust_str = parsed.customer_name
    if cust_str:
        # Find or create customer
        res = await db.execute(select(Customer).where(Customer.name.ilike(cust_str)))
        customer = res.scalar_one_or_none()
        if not customer:
            customer = Customer(name=cust_str.title(), total_credit=0.0)
            db.add(customer)
            await db.flush()
        
        sale.customer_id = customer.id


    logger.info(
        f"Sale #{sale.id} processed: {len(parsed.items)} items, "
        f"total={total_amount:.2f}"
    )

    # Build response — populate speech fields from SpeechResult if available
    lang_code    = sale.detected_language    or "en"
    lang_name    = sale.language_name        or "English"
    lang_prob    = sale.language_probability or 1.0
    eng_text     = sale.english_transcript   or display_transcript
    rec_prompt   = (
        speech_result.recording_prompt
        if speech_result else
        RECORDING_PROMPTS.get(lang_code, RECORDING_PROMPTS["en"])
    )

    return SaleProcessResponse(
        sale_id              = sale.id,
        status               = "pending_confirmation",
        message              = f"Preview: Sale ready to be confirmed.",
        transcript           = display_transcript,
        english_transcript   = eng_text,
        detected_language    = lang_code,
        language_name        = lang_name,
        language_probability = round(lang_prob, 4),
        recording_prompt     = rec_prompt,
        items_parsed         = len(parsed.items),
        total_amount         = round(total_amount, 2),
        customer_name        = parsed.customer_name,
        payment_status       = parsed.payment_status,
        missing_products     = [],
        needs_action         = False,
        inventory_updated    = False,
        credit_updated       = False,
        parsed_item_details  = parsed_item_details,
    )

async def confirm_sale_action(db: AsyncSession, sale: Sale) -> SaleProcessResponse:
    if sale.status != SaleStatus.PENDING:
        raise ValueError("Sale is not pending.")
        
    for db_item in sale.items:
        await apply_sale(db, db_item)

    sale.status = SaleStatus.PROCESSED
    
    credit_updated = False
    if sale.customer_id:
        unpaid = sale.total_amount - sale.amount_paid
        if unpaid > 0:
            res = await db.execute(select(Customer).where(Customer.id == sale.customer_id))
            customer = res.scalar_one()
            customer.total_credit += unpaid
            
            credit_tx = CreditTransaction(
                customer_id=customer.id,
                sale_id=sale.id,
                amount=unpaid,
                transaction_type=TransactionType.CREDIT
            )
            db.add(credit_tx)
            credit_updated = True
            logger.info(f"Credit applied to {customer.name}: +₹{unpaid}")
            logger.info(f"🔔 [EVENT: SMS TRIGGER] Send SMS to {customer.name}: 'Payment of ₹{unpaid} is pending for today's purchase.'")

    await db.commit()
    
    lang_code  = sale.detected_language or "en"
    lang_name  = sale.language_name or "English"
    rec_prompt = RECORDING_PROMPTS.get(lang_code, RECORDING_PROMPTS["en"])
    
    customer_name = None
    if sale.customer_id:
        res = await db.execute(select(Customer).where(Customer.id == sale.customer_id))
        c = res.scalar_one_or_none()
        if c:
            customer_name = c.name
    
    return SaleProcessResponse(
        sale_id              = sale.id,
        status               = "processed",
        message              = f"Sale confirmed and inventory updated.",
        transcript           = sale.raw_text or "",
        english_transcript   = sale.english_transcript or "",
        detected_language    = lang_code,
        language_name        = lang_name,
        language_probability = sale.language_probability or 1.0,
        recording_prompt     = rec_prompt,
        items_parsed         = len(sale.items),
        total_amount         = sale.total_amount,
        customer_name        = customer_name,
        payment_status       = sale.payment_status.value if sale.payment_status else "paid",
        missing_products     = [],
        needs_action         = False,
        inventory_updated    = True,
        credit_updated       = credit_updated,
        parsed_item_details  = []
    )


# ─────────────────────────────────────────────────────────────────────────────
# CRUD helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_sale(db: AsyncSession, sale_id: int) -> Optional[Sale]:
    result = await db.execute(
        select(Sale)
        .options(selectinload(Sale.items))
        .where(Sale.id == sale_id)
    )
    return result.scalar_one_or_none()


async def get_all_sales(db: AsyncSession) -> list:
    result = await db.execute(
        select(Sale)
        .options(selectinload(Sale.items))
        .order_by(Sale.created_at.desc())
    )
    return list(result.scalars().all())
