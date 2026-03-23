"""
Query Agent — AI-powered chatbot pipeline orchestrator.

NEW PIPELINE (AI-first):
  User query
    ↓  detect_language()           → "en" | "ta" | "tanglish"
    ↓  fetch_inventory_context()   → comprehensive DB snapshot
    ↓  llm_service.answer_with_context() → AI generates conversational answer
    ↓  (fallback: template if LLM fails)
    ↓
  Return { intent, answer_text, detected_language, is_db_sourced }

The LLM receives structured, factual data from the database and writes the
answer itself. No fixed templates for simple queries. This enables:
  - Free-form conversational questions ("What's the cheapest product?")
  - Multi-intent queries ("Price and stock of cement?")
  - Cross-inventory analytics ("Which product has the highest margin?")
  - Natural multilingual responses
"""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.services.intent_classifier import (
    INTENT_ANALYTICS,
    INTENT_GREETING,
    INTENT_LOW_STOCK,
    INTENT_PRICE,
    INTENT_PRODUCT,
    INTENT_STOCK,
    INTENT_UNKNOWN,
    detect_intent,
)
from app.services.language_detector import detect_language
from app.services.llm_service import llm_service
from app.services.template_builder import build_template
from app.tools.inventory_tools import (
    get_inventory_summary,
    get_low_stock_products,
    get_stock_for_product,
    get_all_products,
)


# ── Filler words for product name extraction ───────────────────────────────────
_FILLER_WORDS = [
    # Tanglish
    "evlo iruku", "evlo irukku", "stock evlo", "vilai enna", "enna vilai",
    "rate enna", "sollu", "paaru", "paarungo", "kudu",
    "evlo", "evvlo", "iruku", "irukku", "vilai", "stock", "price",
    "rate", "enna", "quantity", "ithu",
    # English
    "what is the price of", "how much is", "how much does",
    "what is the stock of", "how many", "tell me about",
    "price of", "cost of", "stock of", "how much",
    # Tamil Unicode
    "விலை என்ன", "எவ்வளவு இருக்கு", "சொல்லு",
]


def _extract_product_name(text: str) -> str:
    cleaned = text.lower()
    for filler in sorted(_FILLER_WORDS, key=len, reverse=True):
        cleaned = cleaned.replace(filler.lower(), " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else text


# ── Context builder ─────────────────────────────────────────────────────────────

async def _build_inventory_context(
    db: AsyncSession,
    intent: str,
    text: str,
) -> dict[str, Any]:
    """
    Fetch relevant inventory data from the database and structure it for LLM context.
    
    For product-specific intents: fetch the matching product.
    For analytics/low-stock: fetch summary or all low-stock items.
    For general queries: provide a brief inventory snapshot.
    """
    context: dict[str, Any] = {}

    if intent in (INTENT_PRICE, INTENT_STOCK, INTENT_PRODUCT):
        product_hint = _extract_product_name(text)
        logger.debug(f"Looking up product: '{product_hint}'")
        product = await get_stock_for_product(db, product_hint)
        if product:
            context["matched_product"] = product
        else:
            # Provide all products so the LLM can suggest similar ones
            all_prods = await get_all_products(db)
            context["product_not_found"] = product_hint
            context["available_products"] = [
                {"name": p.name, "price": p.selling_price, "stock": p.current_stock, "unit": p.unit}
                for p in all_prods[:20]  # Limit to 20 to save tokens
            ]

    elif intent == INTENT_LOW_STOCK:
        raw = await get_low_stock_products(db, threshold=20)
        context["low_stock_products"] = [
            {"name": p.name, "stock": p.current_stock, "unit": p.unit, "reorder_point": p.reorder_point}
            for p in raw
        ]
        summary = await get_inventory_summary(db)
        context["inventory_summary"] = summary

    elif intent == INTENT_ANALYTICS:
        summary = await get_inventory_summary(db)
        context["inventory_summary"] = summary
        all_prods = await get_all_products(db)
        context["all_products"] = [
            {
                "name": p.name,
                "selling_price": p.selling_price,
                "cost_price": p.cost_price,
                "stock": p.current_stock,
                "unit": p.unit,
            }
            for p in all_prods[:20]
        ]

    elif intent == INTENT_UNKNOWN:
        # For unknown queries, provide a full snapshot so the LLM can answer
        # free-form questions ("what's the cheapest item?")
        all_prods = await get_all_products(db)
        summary = await get_inventory_summary(db)
        context["inventory_summary"] = summary
        context["all_products"] = [
            {
                "name": p.name,
                "selling_price": p.selling_price,
                "cost_price": p.cost_price,
                "stock": p.current_stock,
                "unit": p.unit,
            }
            for p in all_prods[:20]
        ]

    return context


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process_query(
    db: AsyncSession,
    text: str,
    language: str | None = None,
) -> dict:
    """
    Full AI-powered pipeline: text → intent → DB context → LLM answer.

    Args:
        db:       AsyncSession.
        text:     User query (Tamil / Tanglish / English).
        language: Pre-detected language code or None (auto-detect).
    """
    # ── Step 1: Language detection ────────────────────────────────────────────
    if language is None:
        language, _ = detect_language(text)
    logger.info(f"Language: {language} | Query: {text[:80]}")

    # ── Step 2: Intent detection ──────────────────────────────────────────────
    intent = detect_intent(text)
    logger.info(f"Intent: {intent}")

    # ── Step 3: Greetings → use LLM generate() directly ──────────────────────
    if intent == INTENT_GREETING:
        try:
            ai_reply = await llm_service.generate(
                user_message=text,
                temperature=0.5,
                max_tokens=100,
            )
            if ai_reply:
                return {"intent": intent, "answer_text": ai_reply, "detected_language": language, "is_db_sourced": False}
        except Exception as exc:
            logger.warning(f"LLM greeting failed: {exc}")
        # Fallback
        return {
            "intent": intent,
            "answer_text": build_template(intent=intent, language=language),
            "detected_language": language,
            "is_db_sourced": False,
        }

    # ── Step 4: Fetch relevant inventory context from DB ──────────────────────
    context = await _build_inventory_context(db, intent, text)
    is_db_sourced = bool(context)

    # ── Step 5: Ask the LLM to answer using the DB context ───────────────────
    if context and settings.GROQ_API_KEY:
        try:
            ai_answer = await llm_service.answer_with_context(
                user_query=text,
                context=context,
                language=language,
            )
            if ai_answer:
                logger.info(f"AI answer generated: {ai_answer[:120]}")
                return {
                    "intent": intent,
                    "answer_text": ai_answer,
                    "detected_language": language,
                    "is_db_sourced": is_db_sourced,
                }
        except Exception as exc:
            logger.warning(f"LLM answer_with_context failed: {exc}")

    # ── Step 6: Fallback to template builder ─────────────────────────────────
    logger.info("Falling back to template builder.")
    
    # Rebuild args for template_builder from context
    product  = context.get("matched_product")
    products = context.get("low_stock_products")
    summary  = context.get("inventory_summary")
    
    template = build_template(
        intent=intent,
        language=language,
        product=product,
        products=products,
        summary=summary,
    )

    return {
        "intent": intent,
        "answer_text": template,
        "detected_language": language,
        "is_db_sourced": is_db_sourced,
    }
