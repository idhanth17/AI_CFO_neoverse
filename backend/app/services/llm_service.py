"""
LLM Service — Groq Cloud API (llama-3.3-70b-versatile).

NEW DESIGN: The LLM is the PRIMARY answer engine.
Inventory data is fetched from the database first, then injected into the
LLM prompt as a "ground truth context" block. The LLM writes a conversational
response grounded on that context, so there is no hallucination risk.

Key methods
───────────
answer_with_context()  → primary: LLM answers using injected DB context
polish()               → fallback: LLM improves fluency of a pre-built template
generate()             → generic: greetings / unknown intents
"""
from __future__ import annotations

import json
from typing import Any

from groq import AsyncGroq

from app.core.config import settings
from app.core.logger import logger


# ── System prompts ─────────────────────────────────────────────────────────────

_CONTEXT_SYSTEM_PROMPT = """\
You are an intelligent AI CFO assistant for a Tamil Nadu hardware/provisions shop.
You have access to live inventory data that is injected into every request.

RULES:
1. Use ONLY the inventory data provided to answer factual questions (prices, stock, etc).
2. If the data shows a product, answer confidently with exact numbers — do NOT say "I don't know".
3. If a product is NOT in the inventory data, say it's not found in inventory.
4. Detect the language of the user query and respond in the SAME language:
   - English query → English response
   - Tamil (தமிழ்) query → Tamil response  
   - Tanglish (e.g., "LED bulb price sollu") → Tanglish/Tamil response
5. Be conversational and concise (2–3 sentences max). No markdown formatting.
6. For analytics or summary questions, provide a helpful overview.
7. For greetings, respond warmly and ask how you can help with inventory queries.
"""

_POLISH_SYSTEM_PROMPT = """\
You are a multilingual shop assistant in Tamil Nadu.
You receive a pre-written answer with product data. Improve its fluency and tone.
Do NOT change numbers, prices, or product names. Keep it to 1–2 sentences.
No markdown. If the message says respond in Tamil, reply in Tamil script.
"""

_GENERAL_SYSTEM_PROMPT = """\
You are a friendly AI CFO assistant for a small shop in Tamil Nadu.
Reply in the same language as the user (English/Tamil/Tanglish).
Keep responses conversational and to 2 sentences. No markdown.
"""


class LLMService:
    """Interface to the Groq Cloud API."""

    def __init__(self) -> None:
        self.api_key: str = settings.GROQ_API_KEY
        self.model:   str = settings.GROQ_MODEL
        self._client: AsyncGroq | None = None

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            if not self.api_key:
                logger.warning("GROQ_API_KEY not set — LLM disabled.")
                self._client = AsyncGroq(api_key="missing-key")
            else:
                self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    # ── Core helper ────────────────────────────────────────────────────────────

    async def _chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.4,
        max_tokens: int = 300,
    ) -> str:
        try:
            logger.debug(f"Calling Groq '{self.model}' …")
            completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.9,
            )
            reply = (completion.choices[0].message.content or "").strip()
            logger.info(f"LLM reply: {reply[:150]}")
            return reply
        except Exception as exc:
            logger.error(f"Groq API error: {exc}")
            return ""

    # ── PRIMARY: answer with injected DB context ───────────────────────────────

    async def answer_with_context(
        self,
        user_query: str,
        context: dict[str, Any],
        language: str = "en",
    ) -> str:
        """
        Primary AI answer: the LLM receives the user's query AND structured
        inventory data fetched from the database, then writes a full answer.

        Args:
            user_query: Original user text.
            context:    Dict of inventory data pulled from DB (prices, stock, etc).
            language:   Detected language code ("en" | "ta" | "tanglish").

        Returns:
            AI-generated answer string, or "" on failure (caller should fall back).
        """
        if not self.api_key:
            return ""

        # Serialise the inventory context as clean JSON for the LLM
        context_block = json.dumps(context, ensure_ascii=False, indent=2)

        lang_hint = ""
        if language in ("ta", "tanglish"):
            lang_hint = "\n\nIMPORTANT: The user wrote in Tamil/Tanglish. Reply in Tamil or Tanglish accordingly."
        else:
            lang_hint = "\n\nIMPORTANT: The user wrote in English. Reply in English."

        user_msg = (
            f"=== LIVE INVENTORY DATA (from database) ===\n"
            f"{context_block}\n\n"
            f"=== USER QUERY ===\n"
            f"{user_query}"
            f"{lang_hint}"
        )

        reply = await self._chat(
            system_prompt=_CONTEXT_SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.4,
            max_tokens=300,
        )

        if not reply or len(reply) < 5:
            logger.warning("LLM answer_with_context returned empty string.")
            return ""

        return reply

    # ── FALLBACK: polish a pre-built template ─────────────────────────────────

    async def polish(self, template_text: str, language: str) -> str:
        """Improve the fluency of a template. Used as a fallback."""
        if not self.api_key:
            return template_text

        lang_instruction = (
            "Respond in Tamil (தமிழ்)."
            if language in ("ta", "tanglish")
            else "Respond in English."
        )

        user_msg = (
            f"{lang_instruction}\n\n"
            f"Shop assistant answer to polish (do NOT change numbers or product names):\n"
            f'"{template_text}"'
        )

        polished = await self._chat(
            system_prompt=_POLISH_SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.2,
            max_tokens=150,
        )

        if not polished or len(polished) < 5:
            return template_text
        return polished

    # ── GENERIC: greeetings / unknown ─────────────────────────────────────────

    async def generate(
        self,
        user_message: str,
        context: str | None = None,
        system_override: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 200,
        **kwargs,
    ) -> str:
        """Generic generation for greetings / unknown intents."""
        if not self.api_key:
            return "Sorry, AI is not configured. Please check GROQ_API_KEY."

        sys_prompt = system_override or _GENERAL_SYSTEM_PROMPT
        msg = user_message
        if context:
            msg = f"Shop context:\n{context}\n\nUser: {user_message}"

        reply = await self._chat(
            system_prompt=sys_prompt,
            user_message=msg,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return reply or "Sorry, I couldn't generate a response right now."

    async def is_available(self) -> bool:
        return bool(self.api_key)


# Module singleton
llm_service = LLMService()
