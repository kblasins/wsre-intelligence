"""WSRE Intelligence — FastAPI application.

Runs on localhost:8000 in local development.
Frontend (Vite) runs on localhost:3000 and proxies /api/* here.

No Sentry in local mode. Logs go to stdout + ./logs/app.log.
For production migration points see README → "Going to production later".
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import auth_router, users_router
from app.api.routes.briefs import router as briefs_router
from app.api.routes.market import router as market_router
from app.api.routes.spatial import router as spatial_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.scheduler import start_scheduler, stop_scheduler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

configure_logging()

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup_begin", env=app.extra.get("env", "development"))

    # Verify Postgres reachable
    from sqlalchemy import text

    from app.core.database import engine

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version()"))
        pg_version = (result.scalar() or "")[:60]
        log.info("postgres_connected", version=pg_version)

    # Ensure local data directories exist
    for d in (
        settings.blob_store_local_root,
        settings.briefs_dir,
        settings.backups_dir,
        settings.playwright_state_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)

    # Start background scheduler (scraper cadence + weekly brief)
    await start_scheduler()

    log.info("startup_complete")
    yield

    await stop_scheduler()
    log.info("shutdown")


app = FastAPI(
    title="WSRE Intelligence API",
    version="0.1.0",
    # Docs always available in local mode
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    extra={"env": settings.env},
)

# CORS — localhost only in local mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(market_router)
app.include_router(briefs_router)
app.include_router(admin_router)
app.include_router(spatial_router)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])


@app.get("/api/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version, "env": settings.env}


@app.get("/api/health/db", tags=["ops"])
async def health_db() -> dict[str, object]:
    from sqlalchemy import text

    from app.core.database import engine

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return {"status": "ok", "postgres": bool(result.scalar())}
