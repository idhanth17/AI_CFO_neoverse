"""
OCR Agent
---------
Accepts an uploaded invoice file (image or PDF) and extracts raw text
using Tesseract OCR. PDFs are first converted to images via pdf2image.

Returns: raw OCR text string
"""

import os
import tempfile
from pathlib import Path
from typing import Union

import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from loguru import logger

from app.core.config import settings

# Point pytesseract at the configured Tesseract binary
pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def _preprocess_image(image: Image.Image) -> Image.Image:
    """
    Apply preprocessing to improve OCR accuracy:
    - Convert to greyscale
    - Increase contrast
    - Sharpen edges
    - Upscale if too small
    """
    image = image.convert("L")                          # greyscale
    image = ImageEnhance.Contrast(image).enhance(2.0)   # boost contrast
    image = image.filter(ImageFilter.SHARPEN)            # sharpen

    # Upscale small images — Tesseract works best at 300+ DPI
    w, h = image.size
    if w < 1000:
        scale = 1000 / w
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    return image


def _extract_from_image(file_path: str) -> str:
    """Run Tesseract on a single image file."""
    image = Image.open(file_path)
    image = _preprocess_image(image)

    # PSM 6 = assume a uniform block of text (good for invoices)
    config = "--psm 6 --oem 3"
    text = pytesseract.image_to_string(image, config=config, lang="eng")
    return text.strip()


def _extract_from_pdf(file_path: str) -> str:
    """Convert PDF pages to images, then run OCR on each."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError(
            "pdf2image is required for PDF support. "
            "Install poppler-utils on the system and pdf2image via pip."
        )

    pages = convert_from_path(file_path, dpi=300)
    all_text = []
    for i, page in enumerate(pages):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            page.save(tmp.name, "PNG")
            text = _extract_from_image(tmp.name)
            all_text.append(f"--- Page {i + 1} ---\n{text}")
            os.unlink(tmp.name)

    return "\n\n".join(all_text)


class OCRAgent:
    """
    LangChain-compatible tool wrapper around Tesseract OCR.
    Can be called directly or registered as a LangChain Tool.
    """

    name: str = "ocr_agent"
    description: str = (
        "Extracts raw text from a supplier invoice file (image or PDF) "
        "using Tesseract OCR. Input: file path. Output: raw text string."
    )

    def run(self, file_path: str) -> str:
        """Extract text from an invoice file. Auto-detects image vs PDF."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Invoice file not found: {file_path}")

        suffix = path.suffix.lower()
        logger.info(f"OCR Agent processing: {path.name} (type={suffix})")

        try:
            if suffix == ".pdf":
                text = _extract_from_pdf(file_path)
            elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
                text = _extract_from_image(file_path)
            else:
                raise ValueError(f"Unsupported file type: {suffix}")

            if not text:
                logger.warning(f"OCR returned empty text for {path.name}")
                return ""

            logger.info(f"OCR complete: extracted {len(text)} characters")
            return text

        except Exception as e:
            logger.error(f"OCR Agent failed: {e}")
            raise


# Singleton for import convenience
ocr_agent = OCRAgent()
