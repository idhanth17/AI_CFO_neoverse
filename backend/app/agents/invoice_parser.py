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

from app.agents.normalizer import normalize_receipt


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

    # PaddleOCR outputs boxes out of order or on separate lines.
    # We will use a sliding window over the lines to find: 
    # [Name] -> [Qty/Unit] -> [Price] -> [Total]
    
    lines = [L.strip() for L in text.splitlines() if len(L.strip()) > 1]
    
    # Common units to identify a quantity row
    UNIT_WORDS = {"kg", "gm", "g", "ltr", "l", "pc", "pcs", "nos", "unit", "pkt", "box", "bag", "mtr", "m", "drum"}
    
    i = 0
    while i < len(lines) - 2:
        # Potential item name: not entirely numeric, not a keyword
        name_cand = lines[i]
        skip_words = ["invoice", "bill", "date", "total", "grand", "amount", "sr", "no", "cgst", "sgst", "hsn", "qty", "rate", "discount"]
        is_skip = any(name_cand.lower().startswith(w) for w in skip_words)
        
        # Check if it looks like a hash/part number (e.g., M4510)
        # Or just a regular title
        if is_skip or len(name_cand) < 3 or re.match(r'^[\d.,%]+$', name_cand):
            i += 1
            continue
            
        # The next few lines should contain numbers (qty, price)
        # Let's search ahead up to 7 lines for qty, unit, price, total
        window = lines[i+1 : i+8]
        
        qty = 0.0
        price = 0.0
        total = 0.0
        
        nums_found = []
        for w in window:
            # Check if it's a pure number or "Number Unit"
            w_clean = w.lower().replace(",", "")
            
            # Simple number
            if re.match(r'^\d+(\.\d+)?$', w_clean):
                nums_found.append(float(w_clean))
            # Number with unit
            else:
                parts = w_clean.split()
                if len(parts) >= 1 and re.match(r'^\d+(\.\d+)?$', parts[0]):
                    nums_found.append(float(parts[0]))
                    
        if len(nums_found) >= 2:
            # Assumption: First number is qty, second/third are price/total
            qty = nums_found[0]
            
            # Sometimes HSN code is parsed as the first number.
            # E.g. 3209 (HSN), 10 (Qty), 3100.00 (Price)
            if qty > 1000 and len(nums_found) >= 3:
                qty = nums_found[1]
                price = nums_found[2]
            else:
                price = nums_found[1]
            
            if qty > 0 and price > 0 and qty < 10000 and price < 1000000:
                name = _clean_name(name_cand)
                
                if name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    gst_amt = _compute_gst(price, qty, global_gst, None)
                    items.append(ParsedItem(
                        raw_name=name,
                        quantity=qty,
                        unit_price=price,
                        gst_rate=global_gst,
                        gst_amount=gst_amt,
                        total_amount=round(qty * price + gst_amt, 2),
                    ))
                    logger.debug(f"Parsed item (Window): {name} qty={qty} price={price}")
                    
                i += len(nums_found) # jump ahead to avoid overlapping products
            
        i += 1

    return items


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

class InvoiceParserTool:
    """
    Converts raw OCR text into a structured ParsedInvoice object.
    Uses Groq LLM for accurate spatial reconstruction of PaddleOCR text,
    falling back to regex/heuristics if no API key is present.
    """

    name: str = "invoice_parser"
    description: str = (
        "Parses raw OCR text from a supplier invoice and returns structured "
        "line items with product name, quantity, unit price, GST, and totals."
    )

    async def run(self, ocr_text: str) -> ParsedInvoice:
        if not ocr_text or not ocr_text.strip():
            logger.warning("Invoice parser received empty OCR text")
            return ParsedInvoice(
                supplier_name=None, invoice_number=None,
                invoice_date=None, items=[]
            )

        logger.info(f"Invoice parser processing {len(ocr_text)} characters of OCR text")
        
        from app.core.config import settings
        if settings.GROQ_API_KEY:
            try:
                import json
                from groq import AsyncGroq
                client = AsyncGroq(api_key=settings.GROQ_API_KEY)
                
                prompt = f"""
You are an expert AI parser for Indian supplier receipts.
You are given the raw OCR text string from PaddleOCR. PaddleOCR sometimes extracts text column-by-column rather than line-by-line, meaning the name, quantity, and price might be physically separated by many newlines.

Your task is to precisely reconstruct the parsed line items and header information.

OCR Text:
"{ocr_text}"

Rules:
1. Reconstruct each line item with `raw_name`, `quantity`, `unit_price`, and optionally `gst_rate` (as a number, e.g. 9 or 18) and `gst_amount`, `total_amount`.
2. Ignore header noise, phone numbers, addresses, and standalone numbers.
3. Try to calculate `total_amount = (quantity * unit_price) + gst_amount` if not explicitly found.
4. Extract `supplier_name`, `invoice_number`, `invoice_date` (DD/MM/YYYY or similar string).
5. Extract the global `total_amount` and `total_gst` for the entire invoice.
6. Return purely valid JSON matching this structure exactly (do not add any markdown formatting or tags):

{{
  "supplier_name": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "string or null",
  "total_amount": 0.0,
  "total_gst": 0.0,
  "items": [
    {{
      "raw_name": "string",
      "quantity": 0.0,
      "unit_price": 0.0,
      "gst_rate": 0.0,
      "gst_amount": 0.0,
      "total_amount": 0.0
    }}
  ]
}}
"""
                chat_completion = await client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                
                res = json.loads(chat_completion.choices[0].message.content)
                logger.info("Groq successfully parsed invoice text")
                
                items = []
                for itm in res.get("items", []):
                    items.append(ParsedItem(
                        raw_name=str(itm.get("raw_name", "Unknown")),
                        quantity=float(itm.get("quantity") or 0.0),
                        unit_price=float(itm.get("unit_price") or 0.0),
                        gst_rate=float(itm.get("gst_rate") or 0.0),
                        gst_amount=float(itm.get("gst_amount") or 0.0),
                        total_amount=float(itm.get("total_amount") or 0.0)
                    ))
                
                parsed_inv = ParsedInvoice(
                    supplier_name=res.get("supplier_name"),
                    invoice_number=res.get("invoice_number"),
                    invoice_date=res.get("invoice_date"),
                    total_amount=float(res.get("total_amount") or 0.0),
                    total_gst=float(res.get("total_gst") or 0.0),
                    items=items
                )
                
            except Exception as e:
                logger.error(f"Groq API parsing failed, falling back to heuristic: {e}")
                parsed_inv = self._fallback_parse(ocr_text)
        else:
            parsed_inv = self._fallback_parse(ocr_text)

        # ── Normalize: clean product names & canonicalise units ──
        return await self.normalize_parsed_invoice(parsed_inv)

    async def normalize_parsed_invoice(self, inv: ParsedInvoice) -> ParsedInvoice:
        """Shared normalization logic for both Fast and Slow extraction paths."""
        try:
            dict_data = {"receipt_items": [i.to_dict() for i in inv.items]}
            norm_res = normalize_receipt(dict_data)

            norm_items = []
            for item_dict in norm_res.get("receipt_items", []):
                norm_items.append(ParsedItem(
                    raw_name=item_dict.get("raw_name"),
                    quantity=item_dict.get("quantity"),
                    unit_price=item_dict.get("unit_price"),
                    gst_rate=item_dict.get("gst_rate"),
                    gst_amount=item_dict.get("gst_amount"),
                    total_amount=item_dict.get("total_amount"),
                ))
            inv.items = norm_items
        except Exception as e:
            logger.error(f"Failed to normalize invoice items: {e}")
        return inv

    def _fallback_parse(self, ocr_text: str) -> ParsedInvoice:
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
                
        return ParsedInvoice(
            supplier_name=header.get("supplier_name"),
            invoice_number=header.get("invoice_number"),
            invoice_date=header.get("invoice_date"),
            total_amount=total_amount,
            total_gst=total_gst,
            items=items
        )

# Instantiate the singleton tool
invoice_parser = InvoiceParserTool()
