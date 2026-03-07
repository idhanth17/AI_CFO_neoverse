"""
Database — Async SQLAlchemy engine, session factory, and dependency.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ─── Engine ─────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,          # set True to log all SQL in dev
    connect_args={"check_same_thread": False, "timeout": 30},  # SQLite-specific
)


# ─── Session factory ─────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ─── Base class for all ORM models ───────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─── Table creation ──────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables if they don't exist."""
    # Import models to register them with Base.metadata
    from app.models import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ─── FastAPI dependency ──────────────────────────────────────────────────────

async def get_db() -> AsyncSession:
    """
    Yields an async DB session per request.
    Usage in route:
        db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
