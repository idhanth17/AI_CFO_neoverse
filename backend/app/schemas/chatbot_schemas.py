"""
Pydantic response schemas for chatbot API endpoints.
"""
from typing import Optional
from pydantic import BaseModel, Field


class VoiceQueryResponse(BaseModel):
    """Response for POST /api/chatbot/query (voice + text unified endpoint)."""

    transcription: str = Field(
        ..., description="Text transcribed from audio (empty for text-only queries).",
        examples=["PVC pipe vilai enna"]
    )
    detected_language: str = Field(
        ..., description="Language code: 'ta', 'tanglish', or 'en'.",
        examples=["tanglish"]
    )
    intent: str = Field(
        ..., description="Detected intent category.",
        examples=["price_query"]
    )
    answer_text: str = Field(
        ..., description="Final answer built from DB data.",
        examples=["PVC Pipe 1/2 inch விலை ₹45 ஒரு meterக்கு."]
    )
    audio_file_path: Optional[str] = Field(None, description="Server-side TTS file path.")
    audio_url:       Optional[str] = Field(None, description="URL to download/play TTS audio.")
    error:           Optional[str] = Field(None, description="Error message if any step failed.")


class TextQueryResponse(BaseModel):
    """Response for POST /api/chatbot/text-query (spec-exact shape)."""

    query:             str
    detected_language: str
    intent:            str
    answer_text:       str
    audio_file_path:   Optional[str] = None
    audio_url:         Optional[str] = None
    error:             Optional[str] = None


class ChatbotHealthResponse(BaseModel):
    status:        str
    llm_available: bool
    database:      str
    version:       str
