"""
App Configuration — Settings loaded from .env
"""

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App metadata ─────────────────────────────
    APP_NAME: str = "AI CFO – Small Business Survival Agent"
    APP_VERSION: str = "1.0.0"

    # ── Database ─────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./ai_cfo.db"

    # ── CORS ─────────────────────────────────────
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # ── File storage ─────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 20

    # ── Whisper ───────────────────────────────────
    WHISPER_MODEL: str = "base"      # tiny | base | small | medium

    # ── LLM AI Agent ──────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Chatbot Pipeline ──────────────────────────
    LLM_POLISH_ENABLED: bool = True
    QUERY_CACHE_SIZE: int = 128
    DEBUG: bool = True

    # ── TTS (gTTS) ────────────────────────────────
    TTS_OUTPUT_DIR: str = "./data/audio_output"

    # ── Paths ─────────────────────────────────────
    DATA_DIR: str = "./data"
    MODELS_DIR: str = "./models"
    
    # ── Security ──────────────────────────────────
    # The API key required to access these backend routes from the frontend
    BACKEND_API_KEY: str = ""  # Must be explicitly set in .env for production secure access


settings = Settings()
