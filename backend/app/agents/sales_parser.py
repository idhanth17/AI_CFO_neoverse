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
    raw_text:  str
    items:     List[ParsedSaleItem] = field(default_factory=list)


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

    def run(self, transcript: str) -> ParsedSale:
        if not transcript or not transcript.strip():
            logger.warning("Sales parser received empty transcript")
            return ParsedSale(raw_text=transcript, items=[])

        logger.info(f"Sales parser processing: {transcript!r}")

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

        logger.info(f"Sales parser extracted {len(items)} items from transcript")
        return ParsedSale(raw_text=transcript, items=items)


sales_parser = SalesParserAgent()
