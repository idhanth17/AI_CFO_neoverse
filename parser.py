"""
OCR Document Parser — Deterministic Receipt/Bill Parser
Uses EasyOCR (pure Python, no external binary needed).

Usage:
    python parser.py <image_path>
    python parser.py <image_path> --output result.json
    python parser.py <image_path> --pretty
    python parser.py <image_path> --raw-only
    python parser.py <image_path> --save-db        (save to database)
"""

import re
import sys
import json
import argparse
import asyncio
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent / "backend"))

try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Install with: pip install opencv-python pillow")
    sys.exit(1)

try:
    import easyocr
except ImportError:
    print("[ERROR] EasyOCR not installed.")
    print("Install with: pip install easyocr")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE PRE-PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_image(image_path: str) -> np.ndarray:
    """
    Load and preprocess image to improve OCR accuracy.
    Steps: grayscale → denoise → binarize (Otsu threshold).
    Returns a BGR image (EasyOCR accepts BGR/RGB numpy arrays).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {image_path}")

    # Upscale if the image is too small
    h, w = img.shape[:2]
    if max(h, w) < 1000:
        scale = 1000 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Grayscale → denoise → Otsu binarize
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Convert back to BGR so EasyOCR can handle it
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


# ─────────────────────────────────────────────────────────────────────────────
# EasyOCR SINGLETON  (model is loaded once and reused)
# ─────────────────────────────────────────────────────────────────────────────

_reader = None

def get_reader() -> easyocr.Reader:
    """Lazy-load EasyOCR reader (downloads model on first run, ~100 MB)."""
    global _reader
    if _reader is None:
        print("[INFO] Loading EasyOCR model (first run may download ~100 MB)…", file=sys.stderr)
        _reader = easyocr.Reader(["en"], gpu=False)
        print("[INFO] EasyOCR model ready.", file=sys.stderr)
    return _reader


# ─────────────────────────────────────────────────────────────────────────────
# OCR EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_raw_text(image_path: str) -> str:
    """
    Run EasyOCR on the preprocessed image.
    Returns cleaned, line-ordered text.
    """
    preprocessed = preprocess_image(image_path)
    reader = get_reader()

    # EasyOCR returns list of (bbox, text, confidence)
    results = reader.readtext(preprocessed, detail=1, paragraph=False)

    # Sort top-to-bottom, left-to-right by bounding box top-left corner
    results.sort(key=lambda r: (round(r[0][0][1] / 20) * 20, r[0][0][0]))

    # Reconstruct text preserving line structure
    lines = []
    prev_y = None
    current_line = []

    for (bbox, text, conf) in results:
        if conf < 0.1:          # skip very low-confidence detections
            continue
        top_y = bbox[0][1]
        if prev_y is None or abs(top_y - prev_y) > 15:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [text]
            prev_y = top_y
        else:
            current_line.append(text)

    if current_line:
        lines.append(" ".join(current_line))

    raw = "\n".join(lines)

    # Normalize whitespace
    cleaned_lines = [l.strip() for l in raw.splitlines()]
    return "\n".join(l for l in cleaned_lines if l)


# ─────────────────────────────────────────────────────────────────────────────
# OCR ERROR CORRECTION
# ─────────────────────────────────────────────────────────────────────────────

def correct_ocr(text: str) -> str:
    """Heuristic corrections for common OCR misreads."""
    corrections = [
        (r'(?<=\d)O(?=\d)', '0'),
        (r'(?<=\d)o(?=\d)', '0'),
        (r'(?<=\d)l(?=\d)', '1'),
        (r'(?<=\d)I(?=\d)', '1'),
        (r'\bS(?=\d)', '5'),
        (r'\bB(?=\d)', '8'),
        (r'(?<!\w)Rs\.?', 'Rs.'),
        (r'(?<!\w)INR\.?', 'INR'),
    ]
    for pattern, replacement in corrections:
        text = re.sub(pattern, replacement, text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# FIELD EXTRACTORS
# ─────────────────────────────────────────────────────────────────────────────

def _first_match(patterns, text, flags=re.IGNORECASE):
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).strip()
    return None


def extract_vendor_name(lines):
    candidates = [l for l in lines[:5] if len(l) > 2]
    return candidates[0] if candidates else None


def extract_date(text):
    return _first_match([
        r'\b(\d{2}[\/\-]\d{2}[\/\-]\d{4})\b',
        r'\b(\d{4}[\/\-]\d{2}[\/\-]\d{2})\b',
        r'\b(\d{1,2}\s+\w+\s+\d{4})\b',
    ], text)


def extract_time(text):
    return _first_match([
        r'\b(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)\b',
    ], text)


def extract_bill_number(text):
    return _first_match([
        r'(?:invoice|bill|receipt|order|voucher|txn|transaction)\s*(?:no|num|number|#)[:\s.\-]*([A-Z0-9\-\/]+)',
        r'(?:no|#)[:\s]*([A-Z0-9\-\/]{3,20})',
    ], text)


def extract_currency(text):
    return _first_match([
        r'\b(INR|USD|EUR|GBP|AED|SGD|Rs\.?)\b',
        r'(₹|\$|€|£)',
    ], text)


def _amount(pattern, text):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip().replace(',', '') if m else None


def extract_subtotal(text):
    for p in [
        r'sub[\s\-]?total[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
        r'net\s+amount[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
    ]:
        v = _amount(p, text)
        if v:
            return v
    return None


def extract_tax(text):
    for p in [
        r'(?:cgst|sgst|igst|gst|vat|tax)[:\s@%\w]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
        r'tax(?:es)?[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
    ]:
        v = _amount(p, text)
        if v:
            return v
    return None


def extract_discount(text):
    return _amount(r'discount[:\s]*[₹$€£Rs.]*\s*\-?\s*([\d,]+\.?\d*)', text)


def extract_total(text):
    for p in [
        r'grand\s+total[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
        r'(?:amount\s+payable|payable\s+amount)[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
        r'(?:net\s+payable|total\s+due)[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
        r'\btotal[:\s]*[₹$€£Rs.]*\s*([\d,]+\.?\d*)',
    ]:
        v = _amount(p, text)
        if v:
            return v
    return None


def extract_payment_method(text):
    return _first_match([
        r'(?:payment\s+(?:mode|method|by|via|type))[:\s]*(cash|card|upi|online|credit|debit|net\s*banking|cheque|neft|rtgs|gpay|paytm|phonepe)',
        r'\b(cash|credit\s+card|debit\s+card|upi|gpay|paytm|phonepe|neft|rtgs)\b',
    ], text)


def extract_address(lines, text):
    addr_pattern = re.compile(
        r'(?:address|addr|location|shop|store|branch|flat|plot|door|no\.|street|road|nagar|colony|district|city|state|pin|pincode)[:\s]',
        re.IGNORECASE,
    )
    pincode_pattern = re.compile(r'\b\d{6}\b')

    collected = []
    capture = False
    for line in lines:
        if addr_pattern.search(line):
            capture = True
        if capture and line:
            collected.append(line)
            if pincode_pattern.search(line):
                break
        if len(collected) > 5:
            break

    if collected:
        return " | ".join(collected)

    m = pincode_pattern.search(text)
    if m:
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        return text[start:end].strip() if end != -1 else text[start:].strip()

    return None


def extract_phone(text):
    return _first_match([
        r'(?:phone|mob(?:ile)?|tel(?:ephone)?|contact|ph)[:\s.#]*(\+?[\d\s\-]{7,15})',
        r'(?<!\d)(\+?91[\s\-]?\d{10})(?!\d)',
        r'(?<!\d)(\d{10})(?!\d)',
    ], text)


# ─────────────────────────────────────────────────────────────────────────────
# LINE ITEM DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_items(text):
    items = []

    # Pattern 1: Columnar — "Name   qty   unit_price   total"
    row_pattern = re.compile(
        r'^(.+?)\s{2,}(\d+(?:\.\d+)?)\s+(?:[₹$€£Rs.]*)([\d,]+\.?\d*)\s+(?:[₹$€£Rs.]*)([\d,]+\.?\d*)$',
        re.MULTILINE,
    )
    for m in row_pattern.finditer(text):
        name = m.group(1).strip()
        if re.search(r'\b(item|description|qty|quantity|price|amount|rate)\b', name, re.IGNORECASE):
            continue
        items.append({
            "name": name,
            "quantity": m.group(2),
            "unit_price": m.group(3).replace(',', ''),
            "total_price": m.group(4).replace(',', ''),
        })

    # Pattern 2: "Name @ price x qty  total"
    if not items:
        for m in re.finditer(
            r'^(.+?)\s+@\s*[₹$€£Rs.]*([\d,]+\.?\d*)\s+[xX×]\s*(\d+)\s+[₹$€£Rs.]*([\d,]+\.?\d*)$',
            text, re.MULTILINE,
        ):
            items.append({
                "name": m.group(1).strip(),
                "quantity": m.group(3),
                "unit_price": m.group(2).replace(',', ''),
                "total_price": m.group(4).replace(',', ''),
            })

    # Pattern 3: Two-line items (name on one line, qty/price on next)
    if not items:
        lines = text.splitlines()
        i = 0
        while i < len(lines) - 1:
            name_line = lines[i].strip()
            detail_line = lines[i + 1].strip()
            dm = re.match(
                r'^(\d+(?:\.\d+)?)\s+[₹$€£Rs.]*([\d,]+\.?\d*)\s+[₹$€£Rs.]*([\d,]+\.?\d*)$',
                detail_line,
            )
            if dm and len(name_line) > 2 and not re.search(
                r'\b(total|tax|gst|subtotal|discount|amount|cash|change)\b', name_line, re.IGNORECASE
            ):
                items.append({
                    "name": name_line,
                    "quantity": dm.group(1),
                    "unit_price": dm.group(2).replace(',', ''),
                    "total_price": dm.group(3).replace(',', ''),
                })
                i += 2
                continue
            i += 1

    return items


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_bill(image_path: str) -> dict:
    raw_text = extract_raw_text(image_path)
    corrected = correct_ocr(raw_text)
    lines = corrected.splitlines()

    return {
        "vendor_name":    extract_vendor_name(lines),
        "bill_number":    extract_bill_number(corrected),
        "date":           extract_date(corrected),
        "time":           extract_time(corrected),
        "currency":       extract_currency(corrected),
        "subtotal":       extract_subtotal(corrected),
        "tax":            extract_tax(corrected),
        "discount":       extract_discount(corrected),
        "total":          extract_total(corrected),
        "payment_method": extract_payment_method(corrected),
        "address":        extract_address(lines, corrected),
        "phone":          extract_phone(corrected),
        "items":          extract_items(corrected),
        "raw_text":       corrected,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

async def save_to_database(parsed_data: dict, image_path: str):
    """
    Save parsed receipt data to database.
    Handles async database operations and shuts down the SQLAlchemy engine when
    finished to avoid leaving background threads alive (which can make the CLI
    appear to hang after the script prints its output).
    """
    try:
        from app.db.database import AsyncSessionLocal, init_db, engine
        from app.services.receipt_service import save_parsed_receipt
        
        # Initialize DB tables if needed
        await init_db()
        
        # Save receipt
        async with AsyncSessionLocal() as session:
            receipt = await save_parsed_receipt(
                session,
                parsed_data,
                file_path=str(image_path),
            )
            print(f"[INFO] Receipt saved to database (ID: {receipt.id})", file=sys.stderr)

        # Dispose of the engine so the process can exit cleanly; the async
        # engine creates a connection pool/threadpool that keeps the interpreter
        # alive if not shut down.
        await engine.dispose()
        return receipt.id
    except ImportError as e:
        print(f"[ERROR] Cannot import backend modules: {e}", file=sys.stderr)
        print("[INFO] Make sure backend dependencies are installed: pip install -e backend/", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Failed to save to database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def main():
    ap = argparse.ArgumentParser(
        description="OCR Bill/Receipt Parser — no Tesseract needed, powered by EasyOCR."
    )
    ap.add_argument("image",      help="Path to bill/invoice image (JPG, PNG, BMP, TIFF…)")
    ap.add_argument("--output",   "-o", help="Save JSON to this file (e.g. result.json)", default=None)
    ap.add_argument("--pretty",   "-p", action="store_true", help="Pretty-print JSON")
    ap.add_argument("--raw-only", action="store_true", help="Print raw OCR text only")
    ap.add_argument("--save-db",  "-d", action="store_true", help="Save parsed receipt to database")
    args = ap.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"[ERROR] Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Parsing: {image_path}", file=sys.stderr)

    if args.raw_only:
        print(extract_raw_text(str(image_path)))
        return

    result = parse_bill(str(image_path))
    output = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[INFO] Saved to: {args.output}", file=sys.stderr)
    
    # Save to database if requested
    if args.save_db:
        receipt_id = asyncio.run(save_to_database(result, image_path))
        if receipt_id:
            print(json.dumps({**result, "_receipt_id": receipt_id}, indent=2 if args.pretty else None, ensure_ascii=False))
        else:
            print(output)
    else:
        print(output)

    # The async engine used by the backend may spawn threads for the connection
    # pool and/or async IO.  In earlier versions we observed the CLI hanging
    # after printing the JSON because those worker threads kept the Python
    # process alive; disposing the engine above fixes the problem.


if __name__ == "__main__":
    main()
