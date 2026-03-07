"""
OCR Agent
---------
Accepts an uploaded invoice file (image or PDF) and extracts raw text
using PaddleOCR (replaces legacy Tesseract implementation).
PDFs are first converted to images via pdf2image (requires poppler-utils).

To prevent OpenMP/GIL deadlocks in the Python 3.8 FastAPI event loop, PaddleOCR
is executed as a standalone subprocess (`paddle_worker.py`).

Returns: raw OCR text string
"""

import os
import sys
import json
import time
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, List

from loguru import logger

import base64
from app.core.config import settings

# ─────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────

async def _extract_from_image_async(file_path: str) -> str:
    """Run OCR via persistent PaddleOCR Daemon (eliminates 10s cold-start)."""
    # Move queue to temp dir to avoid triggering uvicorn reloads on every file change
    queue_dir = Path(tempfile.gettempdir()) / "ai_cfo_ocr_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    
    req_id = f"req_{int(time.time()*1000)}"
    req_file = queue_dir / f"{req_id}.req"
    res_file = queue_dir / f"{req_id}.res.json"
    
    try:
        # Create request for the daemon
        with open(req_file, "w") as f:
            json.dump({"img_path": str(file_path), "out_path": str(res_file.absolute())}, f)
            
        # Poll for response file
        start_time = time.time()
        while time.time() - start_time < 30: # 30s timeout
            if res_file.exists():
                with open(res_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "error" in data:
                    raise RuntimeError(data["error"])
                return data.get("text", "")
            await asyncio.sleep(0.2)
            
        # If timeout, fallback to cold-start worker (original logic)
        logger.warning(f"OCR Daemon timeout for {req_id}. Falling back to cold-start worker.")
        worker_script = Path(__file__).parent.parent.parent / "paddle_worker.py"
        loop = asyncio.get_running_loop()
        import subprocess
        
        def run_worker():
            return subprocess.run(
                [sys.executable, str(worker_script), file_path, str(res_file.absolute())],
                capture_output=True, check=False
            )
        await loop.run_in_executor(None, run_worker)
        
        if res_file.exists():
            with open(res_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("text", "")
            
        return ""
    finally:
        for f in [req_file, res_file]:
            if f.exists():
                try: f.unlink()
                except: pass

async def _extract_from_pdf_async(file_path: str) -> str:
    """Convert PDF pages to images, then run OCR on each page."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError("pdf2image is required for PDF support.")

    loop = asyncio.get_running_loop()
    pages = await loop.run_in_executor(None, convert_from_path, file_path, 300)
    all_text: List[str] = []

    for i, page in enumerate(pages):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            page.save(tmp.name, "PNG")
            try:
                text = await _extract_from_image_async(tmp.name)
                if text:
                    all_text.append(f"--- Page {i + 1} ---\n{text}")
            finally:
                try: os.unlink(tmp.name)
                except: pass

    return "\n\n".join(all_text)

# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

class OCRAgent:
    """
    Multimodal OCR Agent with Groq Vision High-Speed path.
    """
    name: str = "ocr_agent"
    
    async def try_fast_extraction(self, file_path: str) -> Optional[dict]:
        """Attempts to use Groq Vision for sub-5 second OCR + Parsing."""
        if not settings.GROQ_API_KEY:
            return None
            
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            
            # Encode image to base64
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            
            logger.info("Sending image to Groq Vision (Fast Path)...")
            prompt = """
Extract all items from this invoice into a JSON object.
Return ONLY valid JSON with this structure:
{
  "supplier_name": "...",
  "invoice_number": "...",
  "invoice_date": "...",
  "total_amount": 0.0,
  "total_gst": 0.0,
  "items": [{"raw_name": "...", "quantity": 0.0, "unit_price": 0.0, "gst_rate": 0.0, "gst_amount": 0.0, "total_amount": 0.0}]
}
"""
            completion = await client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded_string}"}
                            }
                        ]
                    }
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            res = json.loads(completion.choices[0].message.content)
            logger.info("Groq Vision extraction successful!")
            return res
        except Exception as e:
            logger.warning(f"Groq Vision Fast Path failed: {e}")
            return None

    async def run(self, file_path: str) -> str:
        """Standard Local OCR fallback."""
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        try:
            if suffix == ".pdf":
                return await _extract_from_pdf_async(file_path)
            return await _extract_from_image_async(str(path.absolute()))
        except Exception as e:
            logger.exception("OCR Agent Local Path failed:")
            raise

# Singleton
ocr_agent = OCRAgent()
