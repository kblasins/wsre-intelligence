"""Pytest configuration and shared fixtures.

Test database strategy: all non-canary tests run against wshub_test (a
dedicated test database, NOT wshub). No mocking of the DB layer — mocked
DBs won't catch constraint violations, generated columns, or index behavior.

Each test gets its own NullPool engine to avoid asyncpg event-loop affinity
issues. Tables are created once per session via a sync psycopg2 engine.

Cassette (VCR) files live in tests/cassettes/ for HTTP-dependent scraper tests.
Syrupy snapshot files live in tests/snapshots/ for LLM output regression.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models
from app.core.config import settings
from app.core.database import Base, get_db_session
from app.main import app


# Minimal stub that satisfies Depends(current_active_user)
class _FakeUser:
    id = "00000000-0000-0000-0000-000000000001"
    email = "test@test.local"
    is_active = True
    is_superuser = True
    is_verified = True


_FAKE_USER = _FakeUser()

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from httpx import AsyncClient


# ── Event loop ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.DefaultEventLoopPolicy:
    return asyncio.DefaultEventLoopPolicy()


# ── Schema bootstrap (session-scoped, sync) ────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    """Drop and recreate all ORM tables in wshub_test once per test session.

    Uses settings.test_database_url so tests never touch wshub (production).
    Sync engine avoids asyncio event-loop affinity issues at session scope.

    Prerequisite: createdb -U wsuser wshub_test
    """
    sync_url = str(settings.test_database_url).replace("+asyncpg", "+psycopg2", 1)
    engine = sa.create_engine(sync_url, echo=False)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(sa.text("DROP VIEW IF EXISTS district_velocity_summary CASCADE"))
        conn.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS district_velocity CASCADE"))
        conn.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS fact_resolved CASCADE"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
    yield
    with engine.begin() as conn:
        conn.execute(sa.text("DROP VIEW IF EXISTS district_velocity_summary CASCADE"))
        conn.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS district_velocity CASCADE"))
        conn.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS fact_resolved CASCADE"))
        Base.metadata.drop_all(conn)
    engine.dispose()


# ── Per-test async session ──────────────────────────────────────────────────────
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test async session on wshub_test with NullPool (no shared connections).

    NullPool ensures every test gets a brand-new asyncpg connection that
    belongs to the current event loop. Rollback/dispose are best-effort —
    PostgreSQL auto-rolls-back on disconnect anyway.
    """
    engine = create_async_engine(str(settings.test_database_url), poolclass=NullPool, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        with contextlib.suppress(Exception):
            await session.rollback()
    with contextlib.suppress(Exception):
        await engine.dispose()


# ── FastAPI test client ─────────────────────────────────────────────────────────
@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the per-test DB session."""
    from httpx import ASGITransport, AsyncClient

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ── Authenticated test client (bypasses JWT) ────────────────────────────────
@pytest.fixture
async def authed_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the per-test DB session with auth bypassed."""
    from httpx import ASGITransport, AsyncClient

    from app.api.routes.auth import current_active_user

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override
    app.dependency_overrides[current_active_user] = lambda: _FAKE_USER

    # Ensure fake user exists in DB so FK constraints on saved_sites pass
    await db_session.execute(
        sa.text("""
            INSERT INTO users (id, email, hashed_password, is_active, is_superuser, is_verified)
            VALUES (:id, :email, 'x', true, true, true)
            ON CONFLICT DO NOTHING
        """),
        {"id": _FAKE_USER.id, "email": _FAKE_USER.email},
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
