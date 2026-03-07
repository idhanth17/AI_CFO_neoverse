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

    # ── OCR ──────────────────────────────────────
    # Windows default; override in .env if needed
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    # ── Whisper ───────────────────────────────────
    WHISPER_MODEL: str = "base"      # tiny | base | small | medium

    # ── LLM AI Agent ──────────────────────────────
    GROQ_API_KEY: str = ""


settings = Settings()
