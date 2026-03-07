"""
Speech Processing Agent — Multilingual
---------------------------------------
Converts a shopkeeper's voice recording into text using OpenAI Whisper
(offline model, no API key needed).

Supported languages (auto-detected):
  • English   (en)
  • Tamil     (ta)
  • Malayalam (ml)
  • Hindi     (hi)
  • Kannada   (kn)

For non-English speech the agent:
  1. Transcribes in the detected native language.
  2. Translates the transcript to English using Whisper's built-in
     translation task (no extra library required).

The shopkeeper speaks naturally in any supported language:
  Tamil  : "இரண்டு கிலோ அரிசி மற்றும் ஐந்து சோப்புகள் விற்றேன்"
  Hindi  : "दो किलो चावल और पाँच साबुन बेचे"
  English: "Sold 2 kg rice and 5 soaps"

Both the original transcript and the English translation are returned
so the Sales Parser can always work on the English text.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger

from app.core.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Supported languages
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "ta": "Tamil",
    "ml": "Malayalam",
    "hi": "Hindi",
    "kn": "Kannada",
}

# Whisper language codes accepted by the model.transcribe(language=...) call.
# None → Whisper auto-detects among all languages (we restrict afterward).
WHISPER_LANG_CODES = set(SUPPORTED_LANGUAGES.keys())

# Human-readable prompts in each language so the model knows what to expect.
LANGUAGE_PROMPTS: dict[str, str] = {
    "en": "The shopkeeper is describing today's sales in English.",
    "ta": "கடை உரிமையாளர் இன்றைய விற்பனையை விவரிக்கிறார்.",
    "ml": "കടക്കാരൻ ഇന്നത്തെ വിൽപ്പന വിവരിക്കുന്നു.",
    "hi": "दुकानदार आज की बिक्री का विवरण दे रहा है।",
    "kn": "ಅಂಗಡಿಯವರು ಇಂದಿನ ಮಾರಾಟವನ್ನು ವಿವರಿಸುತ್ತಿದ್ದಾರೆ.",
}

# UI prompts shown to shopkeeper before recording — in each language
RECORDING_PROMPTS: dict[str, str] = {
    "en": "Please speak clearly — describe the items sold today.",
    "ta": "தயவுசெய்து தெளிவாகப் பேசுங்கள் — இன்று விற்கப்பட்ட பொருட்களைக் கூறுங்கள்.",
    "ml": "ദയവായി വ്യക്തമായി സംസാരിക്കുക — ഇന്ന് വിൽക്കപ്പെട്ട ഉൽപ്പന്നങ്ങൾ വിവരിക്കുക.",
    "hi": "कृपया स्पष्ट रूप से बोलें — आज बेचे गए सामान का विवरण दें।",
    "kn": "ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟವಾಗಿ ಮಾತನಾಡಿ — ಇಂದು ಮಾರಾಟವಾದ ಸರಕುಗಳನ್ನು ವಿವರಿಸಿ.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SpeechResult:
    """
    Complete result from one speech recognition call.

    Attributes
    ----------
    native_transcript : str
        Verbatim text in the detected language.
    english_transcript : str
        English translation of the transcript (identical to native_transcript
        when the detected language is already English).
    detected_language : str
        ISO 639-1 language code, e.g. "ta", "hi", "en".
    language_name : str
        Human-readable language name, e.g. "Tamil".
    language_probability : float
        Whisper's confidence in the detected language (0–1).
    recording_prompt : str
        Suggested prompt text to display to the shopkeeper before recording,
        in the detected language (useful for UI).
    """
    native_transcript:    str
    english_transcript:   str
    detected_language:    str
    language_name:        str
    language_probability: float
    recording_prompt:     str


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class SpeechAgent:
    """
    Offline multilingual speech-to-text using Whisper.

    * Auto-detects the spoken language.
    * Transcribes in the native language.
    * Translates to English when needed (Whisper built-in translation).
    * Model stays in memory after first load (lazy-loading on first call).
    """

    def __init__(self) -> None:
        self._model = None          # lazy-loaded on first use
        self._model_name: str = settings.WHISPER_MODEL

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Lazy-load the Whisper model once."""
        if self._model is not None:
            return
        try:
            import whisper
            logger.info(f"Loading Whisper model: {self._model_name}")
            self._model = whisper.load_model(self._model_name)
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.warning(
                "openai-whisper not installed — speech input unavailable. "
                "Install with: pip install openai-whisper"
            )
            self._model = None
        except Exception as exc:
            logger.error(f"Failed to load Whisper model: {exc}")
            self._model = None

    def _detect_language(self, audio_path: str) -> tuple[str, float]:
        """
        Use Whisper's language detection on a short audio segment.
        Returns (iso_code, probability).  Falls back to 'en' on error.
        """
        try:
            import whisper
            import torch

            audio = whisper.load_audio(audio_path)
            audio = whisper.pad_or_trim(audio)
            mel   = whisper.log_mel_spectrogram(audio).to(self._model.device)

            _, probs = self._model.detect_language(mel)

            # Filter to our supported set
            supported_probs = {
                lang: probs.get(lang, 0.0)
                for lang in SUPPORTED_LANGUAGES
            }
            best_lang = max(supported_probs, key=supported_probs.get)
            best_prob = supported_probs[best_lang]

            logger.info(
                f"Language detection — top supported: {best_lang} "
                f"({best_prob:.1%}). All supported: "
                + ", ".join(f"{k}:{v:.1%}" for k, v in supported_probs.items())
            )
            return best_lang, best_prob

        except Exception as exc:
            logger.warning(f"Language detection failed ({exc}); defaulting to 'en'")
            return "en", 0.0

    def _transcribe(self, audio_path: str, language: str) -> str:
        """Transcribe audio natively in the given language."""
        prompt = LANGUAGE_PROMPTS.get(language, "")
        result = self._model.transcribe(
            audio_path,
            language=language,
            fp16=False,
            verbose=False,
            initial_prompt=prompt,
        )
        return result.get("text", "").strip()

    def _translate_to_english(self, audio_path: str) -> str:
        """
        Use Whisper's built-in translation task to produce an English
        transcript directly from the audio (no external translation API).
        """
        result = self._model.transcribe(
            audio_path,
            task="translate",   # Whisper translates to English
            fp16=False,
            verbose=False,
        )
        return result.get("text", "").strip()

    async def transcribe_file(self, audio_path: str, target_language: Optional[str] = None) -> SpeechResult:
        """
        Full multilingual pipeline for a file path.

        Steps
        -----
        1. If GROQ API is present, use ultra-fast Whisper cloud translation via AsyncGroq.
        2. Else fallback to local Whisper.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        logger.info(f"[SpeechAgent] Processing: {path.name}")
        
        # Fast Groq Route
        if settings.GROQ_API_KEY:
            try:
                import json
                from groq import AsyncGroq
                logger.info("[SpeechAgent] Using lightning-fast local AsyncGroq API for STT")
                
                async with AsyncGroq(api_key=settings.GROQ_API_KEY) as client:
                    with open(audio_path, "rb") as file:
                        # Step 1: Raw transcription precisely as spoken (captures messy colloquialisms)
                        groq_language = target_language if target_language and target_language in SUPPORTED_LANGUAGES else None
                        transcription = await client.audio.transcriptions.create(
                            file=(path.name, file.read()),
                            model="whisper-large-v3",
                            prompt="Transcribe the colloquial Indian shopkeeper speech exactly as spoken in Tamil, Hindi, Malayalam, Kannada, or English. Contains terms like cement, items, pipes, etc.",
                            **({"language": groq_language} if groq_language else {})
                        )
                        
                    raw_text = transcription.text.strip()
                    logger.debug(f"[SpeechAgent] Groq transcript received ({len(raw_text)} chars)")

                    if not raw_text:
                        logger.info("[SpeechAgent] Audio transcription is empty (likely silence).")
                        resolved_lang = target_language or "en"
                        return SpeechResult(
                            native_transcript="",
                            english_transcript="",
                            detected_language=resolved_lang,
                            language_name=SUPPORTED_LANGUAGES.get(resolved_lang, "English"),
                            language_probability=1.0,
                            recording_prompt=RECORDING_PROMPTS.get(resolved_lang, RECORDING_PROMPTS["en"]),
                        )

                    # Step 2: Intelligent translation and cleaning via LLaMA 70B
                    translation_prompt = f"""
You are an expert translator specializing in colloquial Indian shopkeeper dialects (Tanglish, Hinglish, Manglish, etc.).
You are given a raw, messy voice transcript from a hardware/grocery shop.
Your job is to:
1. Identify the primary base language spoken (en, ta, hi, ml, kn). Keep it exactly one of these codes.
2. Clean up the native text transcript by removing filler words, but keep it in its original language formatting.
3. Translate the items and quantities perfectly into a natural, conversational English sentence.
4. CRITICAL: If the input language is already English, set BOTH `native_text` and `english_translation` to the cleaned up English string. DO NOT translate English into Tamil or any other language. 

Raw Transcript: "{raw_text}"

Respond STRICTLY in JSON format.
CRITICAL: The 'english_translation' field MUST be a plain natural language text string (like "Sold 5 kg rice to Mark"), NOT a nested JSON object or array.

{{
  "language": "en|ta|hi|ml|kn",
  "native_text": "cleaned up native text",
  "english_translation": "clear english translation string"
}}
"""
                    # Execute fast translation explicitly via async client
                    comp = await client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": translation_prompt},
                            {"role": "user", "content": raw_text}
                        ],
                        temperature=0.0,
                        response_format={"type": "json_object"}
                    )
                    
                    out = comp.choices[0].message.content
                    out_js = json.loads(out)
                    
                    final_english = out_js.get("english_translation", raw_text).strip()
                    resolved_lang = out_js.get("language", target_language or "en") # Changed from detected_language to language
                    
                    logger.info(f"[SpeechAgent] LLaMA translation completed (lang={resolved_lang}, chars={len(final_english)})")
                    
                    # Check for empty or NULL translations
                    if final_english.upper() == "NULL" or not final_english:
                        logger.info(f"[SpeechAgent] LLM returned empty or NULL translation for raw text: {raw_text!r}")
                        final_english = ""
                        final_native = ""
                    else:
                        # The LLM sometimes hallucinates a dict instead of string if it thinks it's extracting items.
                        # Also, the LLM might not return native_text if it's just translating.
                        # For now, we'll use the raw_text as native_text if the LLM doesn't provide it.
                        final_native = out_js.get("native_text", raw_text).strip()

                    if isinstance(final_native, dict):
                        final_native = json.dumps(final_native)
                    if isinstance(final_english, dict):
                        final_english = json.dumps(final_english)
                    
                    # Ensure resolved_lang is one of the supported languages
                    if resolved_lang not in SUPPORTED_LANGUAGES:
                        resolved_lang = "en" # Fallback to English if LLM gives an unsupported language
                    
                    return SpeechResult(
                        native_transcript    = final_native,
                        english_transcript   = final_english,
                        detected_language    = resolved_lang,
                        language_name        = SUPPORTED_LANGUAGES[resolved_lang],
                        language_probability = 1.0,
                        recording_prompt     = RECORDING_PROMPTS[resolved_lang],
                    )
            except Exception as e:
                logger.error(f"[SpeechAgent] Groq API failed, falling back to local Whisper: {e}")

        # Local Whisper Route
        self._load_model()
        if self._model is None:
            raise RuntimeError(
                "Whisper model is not available. "
                "Install openai-whisper: pip install openai-whisper"
            )

        # ① Detect language (or use explicit target)
        if target_language and target_language in SUPPORTED_LANGUAGES:
            detected_lang = target_language
            lang_prob = 1.0  # Explicitly set
            logger.info(f"[SpeechAgent] Using explicit target language: {detected_lang}")
        else:
            detected_lang, lang_prob = self._detect_language(str(path))
            
        lang_name = SUPPORTED_LANGUAGES.get(detected_lang, "Unknown")
        recording_prompt = RECORDING_PROMPTS.get(detected_lang, RECORDING_PROMPTS["en"])

        logger.info(
            f"[SpeechAgent] Detected/Target language: {lang_name} "
            f"({detected_lang}) — {lang_prob:.1%} confidence"
        )

        # ② Transcribe natively
        native_text = self._transcribe(str(path), detected_lang)
        logger.info(f"[SpeechAgent] Native transcript ({lang_name}): {native_text!r}")

        # ③ Translate to English (if not already English)
        if detected_lang == "en":
            english_text = native_text
        else:
            english_text = self._translate_to_english(str(path))
            if not english_text:
                english_text = native_text   # graceful fallback
            logger.info(f"[SpeechAgent] English translation: {english_text!r}")

        return SpeechResult(
            native_transcript    = native_text,
            english_transcript   = english_text,
            detected_language    = detected_lang,
            language_name        = lang_name,
            language_probability = round(lang_prob, 4),
            recording_prompt     = recording_prompt,
        )

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        suffix: str = ".wav",
    ) -> SpeechResult:
        """
        Transcribe raw audio bytes (e.g. from HTTP upload).
        Writes to a temp file, processes, then cleans up.
        """
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            return await self.transcribe_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    # ── Legacy compatibility (plain str) ─────────────────────────────────────

    async def transcribe_file_simple(self, audio_path: str) -> str:
        """
        Backward-compatible helper that returns just the English transcript
        string (mirrors the original API so existing call-sites don't break).
        """
        res = await self.transcribe_file(audio_path)
        return res.english_transcript

    # ── Utility ───────────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Check if Whisper is installed and importable."""
        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def supported_languages() -> dict[str, str]:
        """Return mapping of ISO code → language name."""
        return dict(SUPPORTED_LANGUAGES)

    @staticmethod
    def recording_prompts() -> dict[str, str]:
        """Return per-language prompts to show the shopkeeper before recording."""
        return dict(RECORDING_PROMPTS)


speech_agent = SpeechAgent()
