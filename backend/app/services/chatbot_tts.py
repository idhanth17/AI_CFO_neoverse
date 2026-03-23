"""
Text-to-Speech service for the chatbot.

Uses gTTS (Google TTS, no GPU required, good Tamil support).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logger import logger


def _map_language(language: str) -> str:
    """Map internal language code to gTTS locale string."""
    return {
        "ta":       "ta",
        "tanglish": "ta",   # Tanglish → Tamil TTS
        "en":       "en",
        "hi":       "hi",
    }.get(language, "ta")


def generate_speech(text: str, language: str = "ta") -> Optional[str]:
    """
    Synthesise *text* to a .mp3 file using gTTS.

    Returns:
        Absolute path to the generated audio file, or None on failure.
    """
    if not text:
        return None

    output_dir = Path(settings.TTS_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Deterministic filename so repeated calls reuse the same file
    digest = hashlib.md5(f"{language}:{text}".encode()).hexdigest()[:12]
    out_path = output_dir / f"tts_{digest}.mp3"

    if out_path.exists():
        logger.debug(f"TTS cache hit: {out_path.name}")
        return str(out_path)

    try:
        from gtts import gTTS  # type: ignore
        locale = _map_language(language)
        tts = gTTS(text=text, lang=locale, slow=False)
        tts.save(str(out_path))
        logger.info(f"TTS generated: {out_path.name}")
        return str(out_path)
    except ImportError:
        logger.error("gTTS not installed. Run: pip install gTTS")
        return None
    except Exception as exc:
        logger.error(f"TTS failed: {exc}")
        return None


class TextToSpeechService:
    def synthesize(self, text: str, language: str = "ta") -> Optional[str]:
        return generate_speech(text, language)


text_to_speech_service = TextToSpeechService()
