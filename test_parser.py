import argparse
import sys
import json
import os

try:
    from parser.extractor import extract_receipt_data
except Exception as e:
    print(f"\n[ERROR] Failed to initialize extractor: {e}")
    print("[HINT] Make sure GROQ_API_KEY environment variable is set.")
    sys.exit(1)

from parser.ocr import extract_ocr
from parser.layout import group_lines
from storage.db import init_db
from storage.save_receipt import save_receipt

def parse_receipt(image_path):
    print(f"\n[INFO] Starting OCR extraction for image: {image_path}")

    # ---- Check if image exists ----
    if not os.path.exists(image_path):
        print(f"[ERROR] Image file not found: {image_path}")
        return None

    print("[INFO] Image file located successfully.")

    # ---- Run OCR ----
    try:
        ocr_results = extract_ocr(image_path)
    except Exception as e:
        print(f"[ERROR] OCR extraction failed: {e}")
        return None

    if not ocr_results:
        print("[WARNING] OCR returned no results.")
        return None

    # ---- Group OCR text into lines ----
    try:
        lines = group_lines(ocr_results)
    except Exception as e:
        print(f"[ERROR] Layout grouping failed: {e}")
        return None

    if not lines:
        print("[WARNING] No text lines detected after layout grouping.")
        return None

    # ---- Print extracted text ----
    print("\n[INFO] -------- RAW EXTRACTED TEXT --------")
    for line in lines:
        print(line)
    print("[INFO] ------------------------------------")

    # ---- Send to LLM parser ----
    print("\n[INFO] Sending extracted text to Groq LLM for JSON conversion...")

    try:
        data = extract_receipt_data(lines)
    except Exception as e:
        print(f"[ERROR] Receipt parsing failed: {e}")
        return None

    if not data:
        print("[WARNING] Extractor returned empty data.")
        return None

    # ---- Print parsed JSON ----
    print("\n[INFO] -------- PARSED JSON DATA --------")
    print(json.dumps(data, indent=4))
    print("[INFO] ----------------------------------")

    return data


def main():
    parser = argparse.ArgumentParser(description="Parse a receipt image.")

    parser.add_argument(
        "image",
        nargs="?",
        default="receipt.jpg",
        help="Path to the receipt image"
    )

    parser.add_argument(
        "-p",
        action="store_true",
        help="Compatibility flag (unused)"
    )

    args = parser.parse_args()

    print("\n[INFO] Initializing SQLite database...")

    try:
        init_db()
        print("[INFO] Database initialized successfully.")
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        sys.exit(1)

    result = parse_receipt(args.image)

    if result:
        if isinstance(result, dict) and "error" in result:
            print("\n[ERROR] Groq returned an error during parsing.")
            print(result["error"])
        else:
            print("\n[INFO] Standardizing units and names...")

            try:
                save_receipt(result)
                print("[SUCCESS] Receipt normalized and stored into SQLite successfully!")
            except Exception as e:
                print(f"[ERROR] Failed to save receipt to database: {e}")
    else:
        print("\n[WARNING] Pipeline terminated early due to missing or invalid data.")


if __name__ == "__main__":
    main()