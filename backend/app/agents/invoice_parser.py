"""
Invoice Parsing Tool
--------------------
Converts raw OCR text from a supplier invoice into structured line items.

Strategy:
  1. Rule-based regex parser (fast, no external API needed) — primary
  2. Pattern matching for common Indian invoice formats
  3. Returns a list of ParsedItem dicts with product, qty, price, GST

Example OCR input:
  Rice Basmati 5 kg @ Rs. 60.00  300.00  GST 5%  15.00
  Refined Oil  2 ltr @ 120.00    240.00  GST 18% 43.20
"""

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from loguru import logger


@dataclass
class ParsedItem:
    raw_name:    str
    quantity:    float
    unit_price:  float
    gst_rate:    float       # percentage e.g. 5.0
    gst_amount:  float
    total_amount: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedInvoice:
    supplier_name:  Optional[str]
    invoice_number: Optional[str]
    invoice_date:   Optional[str]
    items:          List[ParsedItem] = field(default_factory=list)
    total_amount:   float = 0.0
    total_gst:      float = 0.0


# ─────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────

SUPPLIER_PATTERNS = [
    r"(?:from|supplier|vendor|bill from)[:\s]+([A-Za-z0-9 &.,'-]+)",
    r"^([A-Z][A-Za-z0-9 &.,'-]{3,40})\s*\n",
]

INVOICE_NO_PATTERNS = [
    r"(?:invoice\s*(?:no|number|#)[.:\s]+)([A-Z0-9/-]+)",
    r"(?:bill\s*no[.:\s]+)([A-Z0-9/-]+)",
]

DATE_PATTERNS = [
    r"(?:date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    r"(\d{2}[/-]\d{2}[/-]\d{4})",
]

LINE_ITEM_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 /().-]{2,40?}?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?:kg|gm|g|ltr|l|pc|pcs|nos|unit|pkt|box|bag|mtr|m)?\s*"
    r"(?:@|at|x)?\s*"
    r"(?:rs\.?|inr|₹)?\s*"
    r"(?P<price>\d+(?:\.\d+)?)\s+"
    r"(?:rs\.?|inr|₹)?\s*"
    r"(?P<amount>\d+(?:\.\d+)?)"
    r"(?:\s+(?:gst|tax|igst|cgst|sgst)?\s*"
    r"(?P<gst_rate>\d+(?:\.\d+)?)%?)?"
    r"(?:\s+(?:rs\.?|inr|₹)?\s*(?P<gst_amt>\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)

SIMPLE_LINE_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 /().-]{2,35}?)\s{2,}"
    r"(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?:rs\.?|inr|₹)?\s*(?P<price>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

GST_RATE_LINE = re.compile(r"(?:gst|tax)\s*[@:]?\s*(\d+(?:\.\d+)?)%", re.IGNORECASE)

TOTAL_PATTERN = re.compile(
    r"(?:total|grand\s*total|net\s*amount)[:\s]+(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

def _extract_header(text: str) -> Dict[str, Optional[str]]:
    header: Dict[str, Optional[str]] = {
        "supplier_name": None,
        "invoice_number": None,
        "invoice_date": None,
    }

    for pattern in INVOICE_NO_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            header["invoice_number"] = m.group(1).strip()
            break

    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            header["invoice_date"] = m.group(1).strip()
            break

    for pattern in SUPPLIER_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            header["supplier_name"] = m.group(1).strip()
            break

    return header


def _clean_name(raw: str) -> str:
    name = raw.strip(" -–—|:.,")
    name = re.sub(r"\s{2,}", " ", name)
    return name.title()


def _compute_gst(unit_price: float, quantity: float, gst_rate: float,
                 gst_amt_raw: Optional[str]) -> float:
    if gst_amt_raw:
        try:
            return float(gst_amt_raw)
        except ValueError:
            pass
    return round(unit_price * quantity * gst_rate / 100, 2)


def _parse_line_items(text: str) -> List[ParsedItem]:
    items: List[ParsedItem] = []
    seen_names: set = set()

    global_gst = 0.0
    gst_match = GST_RATE_LINE.search(text)
    if gst_match:
        global_gst = float(gst_match.group(1))

    for line in text.splitlines():
        line = line.strip()
        if len(line) < 8:
            continue

        if re.search(r"^(invoice|bill|date|total|grand|amount|sr\.?\s*no|#|sl)", line, re.I):
            continue

        match = LINE_ITEM_PATTERN.search(line) or SIMPLE_LINE_PATTERN.search(line)
        if not match:
            continue

        try:
            name = _clean_name(match.group("name"))
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            qty   = float(match.group("qty"))
            price = float(match.group("price"))

            if qty <= 0 or price <= 0 or qty > 10000 or price > 1_000_000:
                continue

            gst_rate_val = global_gst
            gst_amt_raw  = None

            if "gst_rate" in match.groupdict() and match.group("gst_rate"):
                gst_rate_val = float(match.group("gst_rate"))
            if "gst_amt" in match.groupdict():
                gst_amt_raw = match.group("gst_amt")

            gst_amt   = _compute_gst(price, qty, gst_rate_val, gst_amt_raw)
            line_total = round(qty * price + gst_amt, 2)

            items.append(ParsedItem(
                raw_name=name,
                quantity=qty,
                unit_price=price,
                gst_rate=gst_rate_val,
                gst_amount=gst_amt,
                total_amount=line_total,
            ))
            logger.debug(f"Parsed item: {name} qty={qty} price={price} gst={gst_rate_val}%")

        except (ValueError, IndexError) as e:
            logger.debug(f"Skipped line (parse error): {line!r} — {e}")
            continue

    return items


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

class InvoiceParserTool:
    """
    Converts raw OCR text into a structured ParsedInvoice object.
    """

    name: str = "invoice_parser"
    description: str = (
        "Parses raw OCR text from a supplier invoice and returns structured "
        "line items with product name, quantity, unit price, GST, and totals."
    )

    def run(self, ocr_text: str) -> ParsedInvoice:
        if not ocr_text or not ocr_text.strip():
            logger.warning("Invoice parser received empty OCR text")
            return ParsedInvoice(
                supplier_name=None, invoice_number=None,
                invoice_date=None, items=[]
            )

        logger.info(f"Invoice parser processing {len(ocr_text)} characters of OCR text")

        header = _extract_header(ocr_text)
        items  = _parse_line_items(ocr_text)

        total_amount = sum(i.total_amount for i in items)
        total_gst    = sum(i.gst_amount for i in items)

        total_match = TOTAL_PATTERN.search(ocr_text)
        if total_match:
            parsed_total = float(total_match.group(1))
            if abs(parsed_total - total_amount) / max(parsed_total, 1) > 0.15:
                logger.warning(
                    f"Total mismatch: parsed={total_amount:.2f} "
                    f"vs OCR total={parsed_total:.2f}"
                )

        logger.info(
            f"Parsed {len(items)} line items | "
            f"total={total_amount:.2f} | gst={total_gst:.2f}"
        )

        return ParsedInvoice(
            supplier_name=header["supplier_name"],
            invoice_number=header["invoice_number"],
            invoice_date=header["invoice_date"],
            items=items,
            total_amount=round(total_amount, 2),
            total_gst=round(total_gst, 2),
        )


invoice_parser = InvoiceParserTool()
