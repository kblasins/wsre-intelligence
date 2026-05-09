"""Async SQLAlchemy engine and session factory.

Uses asyncpg driver for all production queries.
Alembic migrations use a separate sync engine (psycopg3) via env.py.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

log = structlog.get_logger(__name__)

# Build asyncpg URL from the configured postgres DSN.
# The DSN from Infisical uses postgresql:// scheme; asyncpg needs postgresql+asyncpg://
_raw_url = str(settings.database_url)
if _raw_url.startswith("postgresql://") or _raw_url.startswith("postgres://"):
    _async_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgres://", "postgresql+asyncpg://", 1
    )
else:
    _async_url = _raw_url

engine = create_async_engine(
    _async_url,
    echo=settings.env == "development",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    # Recycle connections after 30 min to handle PgBouncer/load balancer drops
    pool_recycle=1800,
    json_serializer=lambda obj: __import__("orjson").dumps(obj).decode(),
    json_deserializer=lambda s: __import__("orjson").loads(s),
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
