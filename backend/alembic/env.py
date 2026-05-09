"""Alembic migration environment — async-aware, reads config from Settings.

Uses psycopg3 (sync) for migrations since Alembic doesn't yet support
fully async context managers in the run_migrations_online path.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Import all models so Alembic picks up their metadata
from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401  — registers all ORM classes on Base.metadata

config = context.config
fileConfig(config.config_file_name)  # type: ignore[arg-type]

target_metadata = Base.metadata


def _make_url() -> str:
    """Build a psycopg3 async URL from Settings."""
    raw = str(settings.database_url)
    for prefix in ("postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return raw.replace(prefix, "postgresql+psycopg://", 1)
    return raw


def run_migrations_offline() -> None:
    context.configure(
        url=_make_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Expand/contract strategy: never DROP without explicit --rev-range
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_make_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
