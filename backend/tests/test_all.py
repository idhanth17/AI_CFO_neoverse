"""
AI CFO Backend - Automated Test Suite (ASCII-safe output for Windows)
======================================================================
Run from backend/ directory:
    python tests/test_all.py
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

# Ensure app package importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Silence loguru during tests
from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

# ─────────────────────────────────────────────────────────────────────────────
# Test framework helpers
# ─────────────────────────────────────────────────────────────────────────────

results: list = []


def report(name: str, passed: bool, detail: str = "") -> None:
    tag = "[PASS]" if passed else "[FAIL]"
    line = f"  {tag}  {name}"
    if detail:
        # limit detail to ASCII printable to avoid Windows charmap errors
        safe = detail.encode("ascii", errors="replace").decode("ascii")
        line += f"\n         {safe}"
    print(line)
    results.append((name, passed))


def check(condition: bool, name: str, detail: str = "") -> bool:
    report(name, condition, detail)
    return condition


def make_sine_wav(frequency: float = 440.0, duration: float = 1.0,
                  sample_rate: int = 16000) -> bytes:
    """Produce a minimal, valid WAV file with a pure tone (no speech)."""
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            frames += struct.pack("<h", val)
        wf.writeframes(bytes(frames))
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Configuration
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 1 - Configuration & Environment")
print("=" * 60)

try:
    from app.core.config import settings
    check(settings.DATABASE_URL.startswith("sqlite"),
          "DATABASE_URL uses SQLite", settings.DATABASE_URL)
    check(settings.WHISPER_MODEL in ("tiny", "base", "small", "medium", "large"),
          "WHISPER_MODEL is valid", settings.WHISPER_MODEL)
    check(settings.MAX_UPLOAD_MB > 0,
          "MAX_UPLOAD_MB is positive", str(settings.MAX_UPLOAD_MB))
    check(bool(settings.UPLOAD_DIR),
          "UPLOAD_DIR is set", settings.UPLOAD_DIR)
except Exception as exc:
    report("Config import", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Database & Models
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 2 - Database & Models")
print("=" * 60)


async def test_db() -> None:
    try:
        from app.db.database import init_db, AsyncSessionLocal
        from app.models.models import Sale
        from sqlalchemy import select

        await init_db()
        report("Database init (create_all)", True)

        # Verify new multilingual columns exist
        sale_cols = {c.key for c in Sale.__table__.columns}
        new_cols = {"detected_language", "language_name",
                    "language_probability", "english_transcript"}
        missing = new_cols - sale_cols
        check(not missing, "Sale model has all 4 multilingual columns",
              f"Missing: {missing}" if missing else "All present")

        # Insert and read back
        async with AsyncSessionLocal() as session:
            async with session.begin():
                sale = Sale(
                    raw_text="Test sale row",
                    detected_language="en",
                    language_name="English",
                    language_probability=1.0,
                    english_transcript="Test sale row",
                )
                session.add(sale)
                await session.flush()
                sid = sale.id

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Sale).where(Sale.id == sid))
            db_sale = res.scalar_one_or_none()
            check(db_sale is not None, "Sale row persisted to DB")
            check(db_sale.detected_language == "en",
                  "detected_language round-trips correctly")
            check(db_sale.language_probability == 1.0,
                  "language_probability round-trips correctly")
    except Exception as exc:
        report("Database tests", False, str(exc))
        import traceback; traceback.print_exc()


asyncio.run(test_db())


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Schemas
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 3 - Schemas (Pydantic)")
print("=" * 60)

try:
    from app.schemas.schemas import (
        SaleOut, SaleProcessResponse, TextSaleRequest,
        MultilingualSpeechResponse, SupportedLanguagesResponse,
    )

    resp = SaleProcessResponse(
        sale_id=1, status="processed", message="ok",
        transcript="Test", english_transcript="Test",
        detected_language="en", language_name="English",
        language_probability=1.0, recording_prompt="Speak clearly",
        items_parsed=1, total_amount=50.0,
    )
    check(resp.english_transcript == "Test",
          "SaleProcessResponse.english_transcript works")
    check(resp.detected_language == "en",
          "SaleProcessResponse.detected_language works")
    check(resp.recording_prompt == "Speak clearly",
          "SaleProcessResponse.recording_prompt works")

    sr = MultilingualSpeechResponse(
        detected_language="ta", language_name="Tamil",
        language_probability=0.94,
        native_transcript="test native",
        english_transcript="test english",
        recording_prompt="Record prompt",
    )
    check(sr.detected_language == "ta", "MultilingualSpeechResponse.detected_language")
    check(sr.language_probability == 0.94,
          "MultilingualSpeechResponse.language_probability")

    req = TextSaleRequest(text="sold 2 kg rice", language="en")
    check(req.language == "en", "TextSaleRequest.language optional field works")

    req2 = TextSaleRequest(text="sold 2 kg rice")
    check(req2.language is None, "TextSaleRequest.language defaults to None")

    slr = SupportedLanguagesResponse(
        languages={"en": "English", "ta": "Tamil"},
        recording_prompts={"en": "Speak", "ta": "record"},
    )
    check("en" in slr.languages,
          "SupportedLanguagesResponse.languages field works")

except Exception as exc:
    report("Schema tests", False, str(exc))
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Speech Agent
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 4 - Speech Agent (Multilingual)")
print("=" * 60)

try:
    from app.agents.speech_agent import (
        speech_agent, SUPPORTED_LANGUAGES, RECORDING_PROMPTS,
        LANGUAGE_PROMPTS, SpeechResult,
    )

    check(speech_agent.is_available, "Whisper is installed")

    langs = speech_agent.supported_languages()
    for code in ["en", "ta", "ml", "hi", "kn"]:
        check(code in langs, f"Language code '{code}' present in supported_languages()")

    prompts = speech_agent.recording_prompts()
    for code in ["en", "ta", "ml", "hi", "kn"]:
        has = code in prompts and len(prompts[code]) > 0
        check(has, f"recording_prompt for '{code}' is non-empty")

    # SpeechResult dataclass
    sr = SpeechResult(
        native_transcript="hello",
        english_transcript="hello",
        detected_language="en",
        language_name="English",
        language_probability=0.99,
        recording_prompt="Speak clearly",
    )
    check(sr.detected_language == "en", "SpeechResult dataclass instantiates")

    # Full pipeline on a synthetic WAV (sine tone — will get noisy transcript)
    wav_bytes = make_sine_wav(440, 1.5)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    try:
        result = speech_agent.transcribe_file(tmp_path)
        check(isinstance(result, SpeechResult),
              "transcribe_file() returns SpeechResult instance")
        check(len(result.detected_language) == 2,
              "detected_language is 2-char ISO code",
              result.detected_language)
        check(result.detected_language in SUPPORTED_LANGUAGES,
              "detected_language is a supported code",
              result.detected_language)
        check(isinstance(result.language_probability, float),
              "language_probability is float",
              str(result.language_probability))
        check(isinstance(result.native_transcript, str),
              "native_transcript is str")
        check(isinstance(result.english_transcript, str),
              "english_transcript is str")
        check(len(result.recording_prompt) > 0,
              "recording_prompt is non-empty")
    finally:
        os.unlink(tmp_path)

    # backward-compat helper
    wav_bytes2 = make_sine_wav(880, 1.0)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp2:
        tmp2.write(wav_bytes2)
        tmp2_path = tmp2.name
    try:
        simple = speech_agent.transcribe_file_simple(tmp2_path)
        check(isinstance(simple, str),
              "transcribe_file_simple() returns plain str (backward compat)")
    finally:
        os.unlink(tmp2_path)

except Exception as exc:
    report("Speech agent tests", False, str(exc))
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — Sales Parser (existing feature)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 5 - Sales Parser (Existing Feature)")
print("=" * 60)

try:
    from app.agents.sales_parser import sales_parser

    test_cases = [
        ("sold 2 kg rice and 5 soaps", 2),
        ("2 packets biscuits, 1 litre oil", 2),
        ("rice 2 kg, oil 1 litre, sugar 500 gm", 3),
        ("gave 3 soaps and 1 kg sugar to customer", 2),
        ("sold ten pens", 1),
    ]
    for text, expected in test_cases:
        result = sales_parser.run(text)
        check(
            len(result.items) == expected,
            f"Parser: '{text[:45]}' -> {expected} item(s)",
            f"Got {len(result.items)}: {[i.raw_name for i in result.items]}",
        )

except Exception as exc:
    report("Sales parser tests", False, str(exc))
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — Sales Service (text pipeline)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 6 - Sales Service (Text Pipeline)")
print("=" * 60)


async def test_sales_service() -> None:
    try:
        from app.db.database import AsyncSessionLocal, init_db
        from app.models.models import Product
        from app.services.sales_service import process_text_sale
        from sqlalchemy import select

        await init_db()

        # Ensure test product exists
        async with AsyncSessionLocal() as session:
            async with session.begin():
                res = await session.execute(
                    select(Product).where(Product.name == "Rice"))
                if res.scalar_one_or_none() is None:
                    session.add(Product(
                        name="Rice", sku="RICE-001",
                        selling_price=50.0, cost_price=40.0,
                        current_stock=100.0, unit="kg",
                    ))

        async with AsyncSessionLocal() as session:
            async with session.begin():
                resp = await process_text_sale(
                    session, "sold 2 kg rice", language="en")

        check(resp.status == "processed",
              "Text sale: status=processed", resp.message)
        check(resp.items_parsed >= 1,
              "Text sale: items_parsed >= 1", str(resp.items_parsed))
        check(resp.detected_language == "en",
              "Text sale: detected_language=en", resp.detected_language)
        check(resp.english_transcript == "sold 2 kg rice",
              "Text sale: english_transcript preserved")
        check(bool(resp.recording_prompt),
              "Text sale: recording_prompt returned")
    except Exception as exc:
        report("Text sales service", False, str(exc))
        import traceback; traceback.print_exc()


asyncio.run(test_sales_service())


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — Voice Sale Service (synthetic WAV)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 7 - Voice Sale (Synthetic WAV / Whisper)")
print("=" * 60)


async def test_voice_sale() -> None:
    try:
        from app.db.database import AsyncSessionLocal, init_db
        from app.services.sales_service import process_voice_sale

        await init_db()

        save_dir = Path(settings.UPLOAD_DIR) / "audio"
        save_dir.mkdir(parents=True, exist_ok=True)
        test_wav = save_dir / "test_voice_sine.wav"
        test_wav.write_bytes(make_sine_wav(440, 2.0))

        async with AsyncSessionLocal() as session:
            async with session.begin():
                resp = await process_voice_sale(session, str(test_wav))

        check(resp.sale_id > 0,
              "Voice sale: sale_id assigned", str(resp.sale_id))
        check(resp.status in ("processed", "failed"),
              "Voice sale: status is processed or failed", resp.status)
        check(resp.detected_language in {"en", "ta", "ml", "hi", "kn"},
              "Voice sale: detected_language is a supported ISO code",
              resp.detected_language)
        check(isinstance(resp.language_probability, float),
              "Voice sale: language_probability is float",
              str(resp.language_probability))
        check(isinstance(resp.english_transcript, str),
              "Voice sale: english_transcript is str")
        check(bool(resp.recording_prompt),
              "Voice sale: recording_prompt non-empty")

        if test_wav.exists():
            test_wav.unlink()

    except Exception as exc:
        report("Voice sale service", False, str(exc))
        import traceback; traceback.print_exc()


asyncio.run(test_voice_sale())


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — Route Registration
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 8 - FastAPI Route Registration")
print("=" * 60)

try:
    from app.main import app

    route_map: set = set()
    for r in app.routes:
        if hasattr(r, "methods") and hasattr(r, "path"):
            for m in (r.methods or []):
                route_map.add(f"{m} {r.path}")

    required = [
        "POST /api/sales/voice",
        "POST /api/sales/text",
        "GET /api/sales/",
        "GET /api/sales/{sale_id}",
        "POST /api/invoices/upload",
        "GET /api/invoices/",
        "GET /api/inventory/",
        "POST /api/inventory/",
        "GET /api/analytics/dashboard",
        "GET /api/speech/languages",   # NEW
        "POST /api/speech/detect",     # NEW
        "GET /health",
    ]
    for key in required:
        check(key in route_map, f"Route registered: {key}")

except Exception as exc:
    report("Route registration", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — HTTP Integration (TestClient)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 9 - HTTP Integration Tests (TestClient)")
print("=" * 60)

try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import settings

    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update({"X-API-Key": settings.BACKEND_API_KEY})

    # Health
    r = client.get("/health")
    check(r.status_code == 200, "GET /health -> 200")

    # Root
    r = client.get("/")
    check(r.status_code == 200, "GET / -> 200")

    # Inventory list (existing)
    r = client.get("/api/inventory/")
    check(r.status_code == 200, "GET /api/inventory/ -> 200")

    # Sales list (existing)
    r = client.get("/api/sales/")
    check(r.status_code == 200, "GET /api/sales/ -> 200")

    # Invoice list (existing)
    r = client.get("/api/invoices/")
    check(r.status_code == 200, "GET /api/invoices/ -> 200")

    # Speech languages (NEW)
    r = client.get("/api/speech/languages")
    check(r.status_code == 200, "GET /api/speech/languages -> 200")
    if r.status_code == 200:
        body = r.json()
        check("languages" in body, "  response has 'languages' key")
        check("recording_prompts" in body, "  response has 'recording_prompts' key")
        check(set(body.get("languages", {}).keys()) == {"en", "ta", "ml", "hi", "kn"},
              "  All 5 language codes present")

    # Text sale English
    r = client.post("/api/sales/text",
                    json={"text": "sold 2 kg rice and 5 soaps"})
    check(r.status_code in (200, 201),
          "POST /api/sales/text (English) -> 2xx", str(r.status_code))
    if r.status_code in (200, 201):
        body = r.json()
        for field in ["english_transcript", "detected_language",
                      "language_name", "recording_prompt"]:
            check(field in body,
                  f"  /api/sales/text response has '{field}'")

    # Text sale with language hint
    r = client.post("/api/sales/text",
                    json={"text": "sold 3 soaps", "language": "en"})
    check(r.status_code in (200, 201),
          "POST /api/sales/text (language hint) -> 2xx", str(r.status_code))

    # Speech detect — valid WAV
    wav_bytes = make_sine_wav(440, 1.5)
    r = client.post(
        "/api/speech/detect",
        files={"file": ("test.wav", wav_bytes, "audio/wav")},
    )
    check(r.status_code in (200, 500),
          "POST /api/speech/detect (WAV) -> 200 or 500", str(r.status_code))
    if r.status_code == 200:
        body = r.json()
        fields = ["detected_language", "language_name", "language_probability",
                  "native_transcript", "english_transcript", "recording_prompt"]
        for f in fields:
            check(f in body, f"  /api/speech/detect response has '{f}'")
        check(body.get("detected_language") in {"en", "ta", "ml", "hi", "kn"},
              "  detected_language is a supported ISO code",
              str(body.get("detected_language")))

    # Speech detect — wrong type (should 415)
    r = client.post(
        "/api/speech/detect",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    check(r.status_code == 415,
          "POST /api/speech/detect (txt) -> 415", str(r.status_code))

    # Voice sale — WAV upload
    wav_bytes2 = make_sine_wav(660, 1.5)
    r = client.post(
        "/api/sales/voice",
        files={"file": ("voice.wav", wav_bytes2, "audio/wav")},
    )
    check(r.status_code in (200, 201),
          "POST /api/sales/voice (WAV) -> 2xx", str(r.status_code))
    if r.status_code in (200, 201):
        body = r.json()
        for field in ["sale_id", "status", "transcript", "english_transcript",
                      "detected_language", "language_name",
                      "language_probability", "recording_prompt"]:
            check(field in body,
                  f"  /api/sales/voice response has '{field}'",
                  str(body.get(field, "MISSING")))

except RuntimeError as exc:
    if "httpx" in str(exc).lower():
        report("Integration tests (TestClient)", False,
               "httpx not installed. Run: pip install httpx")
    else:
        report("Integration tests", False, str(exc))
        import traceback; traceback.print_exc()
except Exception as exc:
    report("Integration tests", False, str(exc))
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"  Total  : {total}")
print(f"  Passed : {passed} [PASS]")
print(f"  Failed : {failed} {'[FAIL]' if failed else '[PASS]'}")
if failed:
    print("\n  Failed tests:")
    for name, ok in results:
        if not ok:
            print(f"    [FAIL]  {name}")
print()
sys.exit(0 if failed == 0 else 1)
