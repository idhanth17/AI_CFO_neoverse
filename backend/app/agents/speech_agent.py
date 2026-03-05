"""
Speech Processing Agent
-----------------------
Converts a shopkeeper's voice recording into text using OpenAI Whisper
(offline model, no API key needed).

The shopkeeper records short voice notes like:
  "Sold 2 kg rice, 5 soaps, and 1 litre oil today"

The transcript is then passed to the Sales Parser.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional
from loguru import logger

from app.core.config import settings


class SpeechAgent:
    """
    Offline speech-to-text using Whisper.
    Whisper is loaded once and reused (model stays in memory).
    """

    def __init__(self):
        self._model = None          # lazy-loaded on first use
        self._model_name = settings.WHISPER_MODEL

    def _load_model(self):
        """Lazy-load the Whisper model."""
        if self._model is not None:
            return

        try:
            import whisper
            logger.info(f"Loading Whisper model: {self._model_name}")
            self._model = whisper.load_model(self._model_name)
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.warning("openai-whisper not installed — speech input unavailable")
            self._model = None
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self._model = None

    def transcribe_file(self, audio_path: str) -> str:
        """
        Transcribe an audio file to text.
        Supports mp3, wav, m4a, ogg, webm.
        Returns the transcript string (empty string on failure).
        """
        self._load_model()

        if self._model is None:
            raise RuntimeError(
                "Whisper model is not available. "
                "Install openai-whisper: pip install openai-whisper"
            )

        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(f"Transcribing audio file: {path.name}")

        try:
            result = self._model.transcribe(
                str(path),
                language="en",          # set to None for auto-detect
                fp16=False,             # CPU-safe
                verbose=False,
            )
            transcript = result.get("text", "").strip()
            logger.info(f"Transcription complete: {transcript!r}")
            return transcript

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> str:
        """
        Transcribe audio provided as raw bytes (e.g. from an HTTP upload).
        Writes to a temp file, transcribes, then cleans up.
        """
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            return self.transcribe_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    @property
    def is_available(self) -> bool:
        """Check if Whisper is installed and loadable."""
        try:
            import whisper  # noqa
            return True
        except ImportError:
            return False


speech_agent = SpeechAgent()
