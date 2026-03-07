"""
Sales Parsing Agent
-------------------
Converts a natural-language sales transcript (from Whisper) into structured
sale line items with product name and quantity.

Handles various phrasings:
  "sold 2 kg rice and 5 soaps"
  "2 packets biscuits, 1 litre oil, 3 pens"
  "rice 2 kg, oil 1 litre"
  "gave 3 soaps and 1 kg sugar to customer"
"""

import re
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
from loguru import logger


@dataclass
class ParsedSaleItem:
    raw_name:  str
    quantity:  float
    raw_unit:  Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedSale:
    raw_text:       str
    items:          List[ParsedSaleItem] = field(default_factory=list)
    customer_name:  Optional[str] = None
    payment_status: str = "paid"


# ─────────────────────────────────────────────
# Patterns
# ─────────────────────────────────────────────

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "half": 0.5, "quarter": 0.25,
}

UNITS = (
    r"kg|kgs|kilogram|kilograms|"
    r"gm|gram|grams|g|"
    r"ltr|litre|litres|liter|liters|l|"
    r"ml|millilitre|"
    r"pc|pcs|piece|pieces|"
    r"nos|no|number|"
    r"pkt|packet|packets|"
    r"box|boxes|"
    r"bag|bags|"
    r"dozen|dz|"
    r"bottle|bottles|"
    r"unit|units"
)

QTY_FIRST = re.compile(
    rf"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNITS})?\s+(?P<name>[a-z][a-z0-9 /-]{{1,30}})",
    re.IGNORECASE,
)

NAME_FIRST = re.compile(
    rf"(?P<name>[a-z][a-z0-9 /-]{{2,30}}?)\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNITS})?",
    re.IGNORECASE,
)

SEPARATORS = re.compile(r"[,;]|(?:\s+and\s+)|(?:\s+also\s+)|(?:\s+plus\s+)", re.IGNORECASE)

FILLER_WORDS = re.compile(
    r"^(?:sold|give|gave|sell|selling|customer\s+took|taken|issued|"
    r"dispatched|delivered|packed|today|i\s+sold|we\s+sold)\s+",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _replace_number_words(text: str) -> str:
    for word, digit in NUMBER_WORDS.items():
        text = re.sub(rf"\b{word}\b", str(digit), text, flags=re.IGNORECASE)
    return text


def _clean_segment(segment: str) -> str:
    segment = segment.strip()
    segment = FILLER_WORDS.sub("", segment)
    return segment.strip()


def _clean_name(raw: str) -> str:
    name = raw.strip(" -–—|:.,")
    name = re.sub(r"\s{2,}", " ", name)
    return name.title()


def _parse_segment(segment: str) -> Optional[ParsedSaleItem]:
    segment = _clean_segment(segment)
    segment = _replace_number_words(segment)

    if len(segment) < 3:
        return None

    m = QTY_FIRST.search(segment)
    if m:
        name = _clean_name(m.group("name"))
        qty  = float(m.group("qty"))
        unit = m.group("unit")
        if name and qty > 0:
            return ParsedSaleItem(raw_name=name, quantity=qty, raw_unit=unit)

    m = NAME_FIRST.search(segment)
    if m:
        name = _clean_name(m.group("name"))
        qty  = float(m.group("qty"))
        unit = m.group("unit")
        if name and qty > 0:
            return ParsedSaleItem(raw_name=name, quantity=qty, raw_unit=unit)

    return None


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

class SalesParserAgent:
    """
    Parses a natural language sales transcript into structured sale items.
    Works as a standalone service or LangChain Tool.
    """

    name: str = "sales_parser"
    description: str = (
        "Parses a voice transcript describing customer sales into structured "
        "line items with product name and quantity sold."
    )

    def run(self, transcript: str, existing_context: str = None) -> ParsedSale:
        if not transcript or not transcript.strip():
            logger.warning("Sales parser received empty transcript")
            return ParsedSale(raw_text=transcript, items=[])

        logger.info(f"Sales parser processing: {transcript!r}")
        
        # ── LLM AI Agent parsing if Groq API key is present ──
        from app.core.config import settings
        if settings.GROQ_API_KEY:
            try:
                import json
                from groq import Groq
                client = Groq(api_key=settings.GROQ_API_KEY)
                context_prompt = ""
                if existing_context:
                    context_prompt = f'Previous Transcript: "{existing_context}"\nUser correction: "{transcript}"\nCombine the previous context with this correction.'
                else:
                    context_prompt = f'Transcript: "{transcript}"'

                prompt = f"""
You are an expert AI sales data extractor parsing voice transcripts for a hardware shop.
Your goal is to extract the PHYSICAL products sold, the customer name (if any), and the payment status.

CRITICAL RULES:
1. Ignore all conversational filler words (e.g., "mark it", "make it", "actually", "wait", "it should be", "instead", "uhh").
2. Only extract legitimate, physical inventory item names for the `raw_name` field (e.g., "screws", "cement", "drill"). Do NOT extract verbs or pronouns as items.
3. You MUST extract EACH DISTINCT product mentioned as a SEPARATE object in the `items` array. (e.g., "Two PVC pipes and one screwdriver" -> 2 items).
4. Extract the exact numerical quantity for each item (e.g., "Two PVC pipes" -> quantity: 2).
5. If words like 'credit', 'later', 'unpaid', 'due' are used, payment_status is "credit".
6. If it mentions partial payment, payment_status is "partial".
7. Otherwise, default to "paid".
{context_prompt}

Respond strictly with valid JSON only. Format:
{{
  "customer_name": "Name or null",
  "payment_status": "paid|credit|partial",
  "items": [{{"raw_name": "product name", "quantity": 1, "raw_unit": "kg/pcs/etc"}}]
}}
"""
                chat_completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama3-8b-8192",
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                res = json.loads(chat_completion.choices[0].message.content)
                items = [ParsedSaleItem(**itm) for itm in res.get("items", [])]
                
                logger.info(f"AI Agent parsing success: {res}")
                return ParsedSale(
                    raw_text=transcript,
                    items=items,
                    customer_name=res.get("customer_name"),
                    payment_status=res.get("payment_status", "paid")
                )
            except Exception as e:
                logger.error(f"AI Agent (Groq) parsing failed, falling back to regex: {e}")

        # ── Regex Fallback ──
        # Try finding a name like "sold to John" or "gave Mary"
        customer_name = None
        payment_status = "paid"
        
        lower_trans = transcript.lower()
        if "credit" in lower_trans or "unpaid" in lower_trans or "pay later" in lower_trans or "due" in lower_trans:
            payment_status = "credit"
        elif "partial" in lower_trans or "some" in lower_trans:
            payment_status = "partial"
            
        # Basic name extraction heuristic: "to [Name]" 
        name_match = re.search(r"\bto\s+([A-Z][a-z]+)\b", transcript)
        if name_match:
            customer_name = name_match.group(1)

        segments = SEPARATORS.split(transcript)
        items: List[ParsedSaleItem] = []
        seen: set = set()

        for segment in segments:
            item = _parse_segment(segment)
            if item and item.raw_name.lower() not in seen:
                seen.add(item.raw_name.lower())
                items.append(item)
                logger.debug(
                    f"Sale item: {item.raw_name} × {item.quantity} {item.raw_unit or ''}"
                )

        logger.info(f"Sales parser extracted {len(items)} items from transcript (Regex Fallback)")
        return ParsedSale(
            raw_text=transcript, 
            items=items,
            customer_name=customer_name,
            payment_status=payment_status
        )


sales_parser = SalesParserAgent()
