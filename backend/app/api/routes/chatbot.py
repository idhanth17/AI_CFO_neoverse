"""
Chatbot router — text and voice query endpoints for the AI assistant.

Endpoints
─────────
POST /api/chatbot/query       → unified text + audio endpoint
POST /api/chatbot/text-query  → text-only (alias, for testing)
GET  /api/chatbot/health      → system health check
GET  /api/chatbot/audio/{fn}  → serve generated TTS audio file
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.query_agent import process_query
from app.core.config import settings
from app.core.logger import logger
from app.db.database import get_db
from app.schemas.chatbot_schemas import ChatbotHealthResponse, TextQueryResponse, VoiceQueryResponse
from app.services.language_detector import detect_language
from app.services.llm_service import llm_service
from app.services.chatbot_tts import text_to_speech_service

router = APIRouter(prefix="/api/chatbot", tags=["Chatbot AI"])


# ─── Health check ─────────────────────────────────────────────────────────────

@router.get("/health", response_model=ChatbotHealthResponse)
async def chatbot_health():
    """Return chatbot service health status."""
    llm_ok = await llm_service.is_available()
    return ChatbotHealthResponse(
        status="ok",
        llm_available=llm_ok,
        database="connected",
        version=settings.APP_VERSION,
    )


# ─── Text-only query endpoint ─────────────────────────────────────────────────

@router.post("/text-query", response_model=TextQueryResponse)
async def chatbot_text_query(
    query:      str  = Form(...,  description="Query in Tamil, Tanglish, or English"),
    enable_tts: bool = Form(False, description="Generate TTS audio response"),
    db:         AsyncSession = Depends(get_db),
):
    """
    Text-only chatbot query.

    Returns JSON with query, detected_language, intent, answer_text,
    audio_file_path, and error.
    """
    logger.info(f"Chatbot text query: '{query}'")

    lang_code, _ = detect_language(query)

    try:
        result = await process_query(db=db, text=query, language=lang_code)
    except Exception as exc:
        logger.error(f"Chatbot query error: {exc}")
        raise HTTPException(500, str(exc))

    audio_path: Optional[str] = None
    audio_url:  Optional[str] = None

    if enable_tts and result["answer_text"]:
        try:
            audio_path = text_to_speech_service.synthesize(
                text=result["answer_text"], language=lang_code
            )
            if audio_path:
                audio_url = f"/api/chatbot/audio/{Path(audio_path).name}"
        except Exception as exc:
            logger.warning(f"TTS failed: {exc}")

    return TextQueryResponse(
        query=query,
        detected_language=result["detected_language"],
        intent=result["intent"],
        answer_text=result["answer_text"],
        audio_file_path=audio_path,
        audio_url=audio_url,
        error=None,
    )


# ─── Unified voice + text endpoint ───────────────────────────────────────────

@router.post("/query", response_model=VoiceQueryResponse)
async def chatbot_voice_query(
    audio:      Optional[UploadFile] = File(None,  description="Audio file (wav/mp3/m4a)"),
    query:      Optional[str]        = Form(None,  description="Text query (Tamil/Tanglish/English)"),
    enable_tts: bool                 = Form(False, description="Generate TTS audio response"),
    db:         AsyncSession         = Depends(get_db),
):
    """
    Unified voice + text endpoint.

    Accepts EITHER:
    - An audio file  → Whisper STT → pipeline
    - A text query   → pipeline directly
    """
    transcription: str = ""

    # ── 1. Input: audio file ────────────────────────────────────────────────
    if audio and audio.filename:
        try:
            audio_bytes = await audio.read()
            if len(audio_bytes) == 0:
                raise HTTPException(400, "Empty audio file.")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Failed to read audio: {exc}")

        try:
            from app.services.chatbot_tts import text_to_speech_service  # noqa
            # Use the existing speech agent for STT if available
            from app.agents.speech_agent import transcribe_audio_bytes
            stt = transcribe_audio_bytes(audio_bytes, audio.filename)
            transcription = stt.get("text", "")
            logger.info(f"STT: '{transcription}'")
        except ImportError:
            return VoiceQueryResponse(
                transcription="",
                detected_language="unknown",
                intent="unknown",
                answer_text="Voice input is not available right now. Please use text input.",
                error="Speech-to-text module not available. Use text input instead.",
            )
        except Exception as exc:
            logger.error(f"STT error: {exc}")
            raise HTTPException(500, f"STT error: {exc}")

        if not transcription:
            return VoiceQueryResponse(
                transcription="",
                detected_language="unknown",
                intent="unknown",
                answer_text="Could not understand the audio. Please try again.",
                error="Empty transcription.",
            )
        effective_query = transcription

    # ── 1b. Input: text query ───────────────────────────────────────────────
    elif query and query.strip():
        effective_query = query.strip()
        transcription   = effective_query
    else:
        raise HTTPException(400, "Provide either an audio file or a text query.")

    # ── 2. Language detection ───────────────────────────────────────────────
    lang_code, lang_conf = detect_language(effective_query)
    logger.info(f"Language: {lang_code} ({lang_conf:.0%})")

    # ── 3. Pipeline ─────────────────────────────────────────────────────────
    try:
        result = await process_query(db=db, text=effective_query, language=lang_code)
    except Exception as exc:
        logger.error(f"Pipeline error: {exc}")
        raise HTTPException(500, str(exc))

    # ── 4. Optional TTS ─────────────────────────────────────────────────────
    audio_path: Optional[str] = None
    audio_url:  Optional[str] = None

    if enable_tts and result["answer_text"]:
        try:
            audio_path = text_to_speech_service.synthesize(
                text=result["answer_text"], language=lang_code
            )
            if audio_path:
                audio_url = f"/api/chatbot/audio/{Path(audio_path).name}"
        except Exception as exc:
            logger.warning(f"TTS failed (non-fatal): {exc}")

    return VoiceQueryResponse(
        transcription=transcription,
        detected_language=result["detected_language"],
        intent=result["intent"],
        answer_text=result["answer_text"],
        audio_file_path=audio_path,
        audio_url=audio_url,
        error=None,
    )


# ─── Serve generated TTS audio files ──────────────────────────────────────────

@router.get("/audio/{filename}")
async def serve_chatbot_audio(filename: str):
    """Serve a TTS audio file by filename."""
    audio_dir = Path(settings.TTS_OUTPUT_DIR)
    file_path = audio_dir / filename

    # Prevent path traversal
    try:
        file_path.resolve().relative_to(audio_dir.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied.")

    if not file_path.exists():
        raise HTTPException(404, f"Audio file '{filename}' not found.")

    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(path=str(file_path), media_type=media_type)
