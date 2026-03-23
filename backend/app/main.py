"""
AI CFO Backend — Main FastAPI Application
==========================================
Small Business Survival AI Agent

Startup:  uvicorn app.main:app --reload
Docs:     http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.db.database import init_db
from app.core.security import verify_api_key
from app.api.routes import invoices, sales, inventory, analytics, speech
from app.api.routes.chatbot import router as chatbot_router


# ─────────────────────────────────────────────
# Lifespan: startup / shutdown
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # ── Security Validation ──────────────────────
    if not settings.BACKEND_API_KEY or settings.BACKEND_API_KEY == "dev-secret-key":
        logger.error("CRITICAL SECURITY ERROR: BACKEND_API_KEY is not securely set.")
        raise RuntimeError("Refusing to start. You must define a strong BACKEND_API_KEY in the environment (.env) for production and testing. Do not use the default 'dev-secret-key'.")

    # Ensure upload directories exist
    for subdir in ["invoices", "audio"]:
        Path(settings.UPLOAD_DIR, subdir).mkdir(parents=True, exist_ok=True)

    # Create database tables
    await init_db()
    logger.info("Database initialised — all tables ready")

    # Start OCR Daemon in background
    import sys
    import subprocess
    daemon_path = Path(__file__).parent.parent / "paddle_daemon.py"
    daemon_process = None
    if daemon_path.exists():
        logger.info("Starting PaddleOCR Daemon...")
        daemon_process = subprocess.Popen(
            [sys.executable, str(daemon_path)], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )

    yield

    # ── Shutdown ─────────────────────────────
    if daemon_process:
        logger.info("Stopping PaddleOCR Daemon...")
        daemon_process.terminate()
        try: daemon_process.wait(timeout=5)
        except: daemon_process.kill()

    logger.info("AI CFO Backend shutting down")


# ─────────────────────────────────────────────
# App instance
# ─────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AI CFO — Small Business Survival Agent

An agent-based backend that converts supplier invoices and customer voice sales
into structured financial intelligence for small retail shops.

### Purchase Flow
`Invoice Upload → OCR Agent → Invoice Parser → Inventory (+stock)`

### Sales Flow
`Voice Recording → Whisper STT → Sales Parser → Inventory (−stock)`

### AI Agents
- **OCR Agent** — Tesseract OCR on invoice images / PDFs
- **Invoice Parser** — regex-based structured extraction
- **Speech Agent** — Whisper offline multilingual speech-to-text
      (auto-detects English, Tamil, Malayalam, Hindi, Kannada;
       returns native transcript **+** English translation)
- **Sales Parser** — NLP parsing of voice transcripts
- **Profit Intelligence** — Pandas margin analysis per product
- **Demand Prediction** — Moving Average + Linear Regression (Scikit-Learn)
- **Restock Recommender** — lead-time-aware reorder calculation
- **GST Summary** — monthly input-tax aggregation
""",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Routers (Secured by verify_api_key dependency)
# ─────────────────────────────────────────────
app.include_router(invoices.router, dependencies=[Depends(verify_api_key)])
app.include_router(sales.router, dependencies=[Depends(verify_api_key)])
app.include_router(inventory.router, dependencies=[Depends(verify_api_key)])
app.include_router(analytics.router, dependencies=[Depends(verify_api_key)])
app.include_router(speech.router, dependencies=[Depends(verify_api_key)])

# ── Chatbot (no API key required for easy frontend access) ────
app.include_router(chatbot_router)


# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["Health"])
async def root():
    return {
        "message": "AI CFO Backend is running",
        "docs": "/docs",
        "health": "/health",
    }
