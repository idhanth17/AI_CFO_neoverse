"""
Speech Routes — /api/speech

Dedicated endpoints for the multilingual speech recognition feature.

GET  /api/speech/languages          — list supported languages & recording prompts
POST /api/speech/detect             — transcribe audio, detect language, return both
                                      native transcript and English translation
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from loguru import logger

from app.core.config import settings
from app.agents.speech_agent import (
    speech_agent,
    SUPPORTED_LANGUAGES,
    RECORDING_PROMPTS,
)
from app.schemas.schemas import MultilingualSpeechResponse, SupportedLanguagesResponse

router = APIRouter(prefix="/api/speech", tags=["Speech"])

ALLOWED_AUDIO_TYPES = {
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/languages",
    response_model=SupportedLanguagesResponse,
    summary="Supported languages",
)
async def get_supported_languages():
    """
    Return the list of languages supported for auto-detection and transcription,
    together with the per-language recording prompts to display in the UI
    (so the shopkeeper knows what to say and in which language).

    Supported languages: English, Tamil, Malayalam, Hindi, Kannada.
    """
    return SupportedLanguagesResponse(
        languages        = speech_agent.supported_languages(),
        recording_prompts= speech_agent.recording_prompts(),
    )


@router.post(
    "/detect",
    response_model=MultilingualSpeechResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect language & transcribe audio",
)
async def detect_and_transcribe(
    file: UploadFile = File(
        ...,
        description=(
            "Short audio clip from the shopkeeper. "
            "Supported languages: English, Tamil, Malayalam, Hindi, Kannada. "
            "Language is auto-detected — no configuration needed. "
            "Accepted formats: wav, mp3, m4a, ogg, webm."
        ),
    ),
):
    """
    **Multilingual speech detection endpoint.**

    Upload an audio clip in any supported language:
    - **English** · **Tamil** · **Malayalam** · **Hindi** · **Kannada**

    Returns:
    - `detected_language`    — ISO 639-1 code (en / ta / ml / hi / kn)
    - `language_name`        — Human-readable name
    - `language_probability` — Whisper's confidence (0–1)
    - `native_transcript`    — Verbatim text in the detected language
    - `english_transcript`   — English translation
    - `recording_prompt`     — Suggested prompt for the shopkeeper in their language

    This endpoint is useful for:
    1. Previewing recognition before committing a sale.
    2. Displaying the translated text for shopkeeper confirmation.
    3. Debugging / testing multilingual accuracy.
    """
    if not speech_agent.is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Whisper model is not installed. "
                "Run: pip install openai-whisper"
            ),
        )

    base_media_type = file.content_type.split(";")[0].strip()
    if base_media_type not in ALLOWED_AUDIO_TYPES and not base_media_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type: {file.content_type}. "
                   f"Accepted: {', '.join(sorted(ALLOWED_AUDIO_TYPES.keys()))}",
        )

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds {settings.MAX_UPLOAD_MB} MB limit.",
        )

    # Secure File Extension extraction from Content Type map instead of trusting user input
    ext = ALLOWED_AUDIO_TYPES.get(base_media_type, ".wav") # default to wav safely if generic audio/ type sent
    unique_name = f"detect_{uuid.uuid4().hex}{ext}"
    save_dir   = Path(settings.UPLOAD_DIR) / "audio"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path  = save_dir / unique_name

    with open(save_path, "wb") as f:
        f.write(contents)

    logger.info(f"[SpeechDetect] Audio saved for detection: {save_path}")

    try:
        result = await speech_agent.transcribe_file(str(save_path))
    except Exception as exc:
        logger.error(f"[SpeechDetect] Transcription failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech recognition failed: {exc}",
        )
    finally:
        # Clean up the temporary detection file (not a committed sale)
        try:
            if save_path.exists():
                save_path.unlink()
        except Exception:
            pass

    logger.info(
        f"[SpeechDetect] lang={result.language_name} ({result.detected_language}), "
        f"prob={result.language_probability:.1%} | "
        f"native={result.native_transcript!r} | "
        f"english={result.english_transcript!r}"
    )

    return MultilingualSpeechResponse(
        detected_language    = result.detected_language,
        language_name        = result.language_name,
        language_probability = result.language_probability,
        native_transcript    = result.native_transcript,
        english_transcript   = result.english_transcript,
        recording_prompt     = result.recording_prompt,
    )
