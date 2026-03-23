"""
Language detection service.

Detection priority:
1. Tamil Unicode chars present → "ta"
2. Known Tanglish keyword hit  → "tanglish"
3. langdetect says "en" but no English stopwords → "tanglish"
4. langdetect result           → e.g. "en"
5. Fallback                    → "ta"
"""
from __future__ import annotations

import re
from typing import Tuple

from langdetect import LangDetectException, detect_langs

from app.core.logger import logger

# ── Tamil Unicode block (range U+0B80–U+0BFF) detection ──────────────────────
_TAMIL_UNICODE_RE = re.compile(r"[\u0B80-\u0BFF]")

# ── Common English function words (if present → text IS English, not Tanglish) ─
_ENGLISH_STOPWORDS = frozenset(
    {"the", "is", "are", "and", "or", "in", "on", "at", "to", "a", "an",
     "for", "of", "with", "it", "this", "that", "was", "be", "have", "has"}
)

# ── Strictly Tamil words in Latin script (cannot be English) ──────────────────
STRICT_TAMIL_LATIN: frozenset[str] = frozenset({
    "evlo", "evvlo", "evvalavu", "eppo", "ethanai", "enna", "etha", "ethu", "evan", "entha",
    "iruku", "irukku", "irukka", "illai", "illa", "inga", "irunthu", "iruntha", "irundha",
    "vilai", "vila", "kattanam", "bahavil", "porul", "samaan", "jinis",
    "sollu", "sollungo", "paaru", "paarungo", "kudu", "kudungo", "vanga", "vaanga", "edunga", "eththana",
    "theva", "vendum", "venam", "ilaiya", "pudhiya", "pothu", "mudhala", "kadai", "angadi",
    "vanakkam", "nandri", "romba", "nalla", "ayya", "akka", "onnu", "rendu", "moonu", "naalu",
    "aanju", "aaru", "ezhu", "ettu", "ombadhu", "pathu", "nooru", "aayiram",
})

# ── English loanwords commonly used in Tanglish (can be either) ───────────────
ENGLISH_LOAN_WORDS: frozenset[str] = frozenset({
    "rate", "item", "stock", "price", "bill", "cash", "discount",
    "piece", "meter", "roll", "pack", "set", "kilo", "unit", "sir", "anna", "super",
})

# ── Tanglish → Tamil meaning hints (for logging / downstream normalisation) ───
TANGLISH_TO_TAMIL: dict[str, str] = {
    "vilai enna": "விலை என்ன",
    "evlo iruku": "எவ்வளவு இருக்கு",
    "stock evlo": "ஸ்டாக் எவ்வளவு",
    "sollu": "சொல்லு",
    "paaru": "பாரு",
    "vanakkam": "வணக்கம்",
    "illai": "இல்லை",
    "theva": "தேவை",
    "kudu": "கொடு",
    "romba": "ரொம்ப",
}

LANGUAGE_MAP = {
    "ta":       "Tamil",
    "tanglish": "Tanglish (Tamil in Latin script)",
    "en":       "English",
    "hi":       "Hindi",
    "te":       "Telugu",
    "kn":       "Kannada",
    "ml":       "Malayalam",
}


# ─────────────────────────────────────────────────────────────────────────────

def _has_tamil_script(text: str) -> bool:
    """Return True if the text contains any Tamil Unicode characters."""
    return bool(_TAMIL_UNICODE_RE.search(text))


def _has_strict_tamil_keywords(text: str) -> bool:
    """Return True if the text contains at least one strictly Tamil keyword."""
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return bool(words & STRICT_TAMIL_LATIN)


def _has_loan_keywords(text: str) -> bool:
    """Return True if the text contains English loanwords used in Tanglish."""
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return bool(words & ENGLISH_LOAN_WORDS)


def _has_english_stopwords(text: str) -> bool:
    """Return True if the text contains common English function words."""
    words = set(text.lower().split())
    return bool(words & _ENGLISH_STOPWORDS)


def detect_language(text: str) -> Tuple[str, float]:
    """
    Detect the language of *text*.

    Returns:
        (language_code, confidence)
        Possible codes: "ta", "tanglish", "en", or any ISO-639-1 code.
    """
    if not text or not text.strip():
        return "ta", 0.0

    # ── Priority 1: Tamil Unicode script ──────────────────────────────────
    if _has_tamil_script(text):
        return "ta", 1.0

    # ── Priority 2: Strict Tanglish keyword match ──────────────────────────
    if _has_strict_tamil_keywords(text):
        logger.debug("Strict Tanglish keywords detected → 'tanglish'")
        return "tanglish", 0.9

    # ── Priority 3: Ask langdetect ─────────────────────────────────────────
    try:
        langs = detect_langs(text)
        if not langs:
            return "ta", 0.0

        top = langs[0]
        lang_code: str = top.lang
        confidence: float = round(top.prob, 3)

        if lang_code == "en":
            return "en", confidence

        if lang_code not in ("ta", "en") and not _has_english_stopwords(text):
            if _has_strict_tamil_keywords(text):
                logger.debug(f"langdetect returned '{lang_code}'; strict Tamil present → 'tanglish'")
                return "tanglish", confidence
            else:
                # Default to English for unknown Latin script if no strict Tamil
                logger.debug(f"langdetect returned '{lang_code}'; no strict Tamil → 'en' (bias fix)")
                return "en", confidence

        logger.debug(f"Language: {lang_code} ({confidence:.0%})")
        return lang_code, confidence

    except LangDetectException as exc:
        logger.warning(f"langdetect failed: {exc}. Defaulting to 'ta'.")
        return "ta", 0.0


def get_language_name(code: str) -> str:
    """Human-readable language name from ISO code or 'tanglish'."""
    return LANGUAGE_MAP.get(code, code.upper())
