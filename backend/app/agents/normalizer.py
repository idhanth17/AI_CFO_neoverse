"""
Normalizer
----------
Ported from OCR_AGENT_V2 branch's normalizer/normalizer.py.

Provides:
  - normalize_product_name(name) : title-cases and converts inch symbols ("1\"" → "1 Inch")
  - normalize_receipt(data)      : applies unit canonicalisation and name normalisation
                                   to a parsed receipt dict

This is applied as a post-processing step after regex/LLM extraction to
ensure consistent, clean data before database insertion.
"""

import re

# ─────────────────────────────────────────────
# Unit canonicalisation map
# ─────────────────────────────────────────────
UNIT_MAP = {
    "pcs": "nos",
    "pc": "nos",
    "no": "nos",
    "nos": "nos",
    "m": "metre",
    "mtr": "metre",
    "meter": "metre",
    "kg": "kg",
    "kgs": "kg",
    "l": "litre",
    "ltr": "litre",
}


def normalize_product_name(name: str) -> str:
    """
    Clean and normalise a product name:
      - Converts '1"' or '1''' (inch notation) → '1 Inch'
      - Title-cases the result
    """
    if not name:
        return "Unknown Product"
    # Convert '1"' or '1''' to '1 Inch'
    name = re.sub(r'(\d+)\s*"|\'\'', r'\1 Inch', name)
    return name.title().strip()


def normalize_receipt(data: dict) -> dict:
    """
    Normalize a parsed receipt/invoice dict:
      - Fills in missing vendor_name
      - Normalises each item's name, unit, and key names
        (handles both 'description'/'name' and 'unit_price'/'price' variants
         from different LLM extraction outputs)

    Returns the mutated dict.
    """
    if "vendor_name" not in data:
        data["vendor_name"] = "Unknown Vendor"

    normalized_items = []

    for item in data.get("items", []):
        # Handle alternating key names from different LLM/regex extractions
        raw_name  = item.get("description", item.get("name", "Unknown Product"))
        raw_price = item.get("unit_price", item.get("price", 0.0))
        raw_unit  = str(item.get("unit", "nos")).lower().strip()

        normalized_item = {
            "name":      normalize_product_name(raw_name),
            "quantity":  item.get("quantity", 1),
            "unit_price": raw_price,
            "price":     raw_price,       # keep both keys for downstream compat
            "unit":      UNIT_MAP.get(raw_unit, raw_unit),
        }
        normalized_items.append(normalized_item)

    data["items"] = normalized_items
    return data
