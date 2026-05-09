"""Application settings — drawn entirely from environment variables.

Local development: values come from .env.local (gitignored).
Copy .env.example → .env.local and fill in your Anthropic key.

Production migration: every external service has a corresponding env var.
See README → "Going to production later" for the full swap guide.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root — used for resolving local filesystem paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────────
    env: Literal["development", "staging", "production"] = "development"
    secret_key: str = "local-dev-secret-change-before-sharing"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_file: Path = PROJECT_ROOT / "logs" / "app.log"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: PostgresDsn = PostgresDsn(  # type: ignore[assignment]
        "postgresql+asyncpg://wsuser:wspass@localhost:5432/wsre"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    # ── Blob storage ─────────────────────────────────────────────────────────
    # "local" → LocalBlobStore (./data/raw/ on disk)
    # "s3"    → S3BlobStore (not yet implemented — see production guide)
    blob_store_backend: Literal["local", "s3"] = "local"
    blob_store_local_root: Path = PROJECT_ROOT / "data" / "raw"

    # S3 vars — unused until blob_store_backend="s3"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_raw_bucket: str = "ksa-re-raw"
    s3_briefs_bucket: str = "ksa-re-briefs"
    s3_region: str = "eu-central-1"

    # ── Brief output ─────────────────────────────────────────────────────────
    briefs_dir: Path = PROJECT_ROOT / "data" / "briefs"

    # ── Backups ───────────────────────────────────────────────────────────────
    backups_dir: Path = PROJECT_ROOT / "data" / "backups"
    backup_keep_count: int = 14  # keep last N pg_dump files

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    # Monthly hard stop — pause batch jobs when this is hit
    # Set matching hard cap in Anthropic Console workspace settings
    claude_monthly_budget_usd: float = 50.0
    claude_daily_budget_usd: float = 5.0
    claude_per_task_alert_usd: float = 0.10

    # ── Scraping ─────────────────────────────────────────────────────────────
    scraper_live_mode: bool = False
    # KSA residential proxy — optional, improves REGA/Aqar success rate
    ksa_proxy_url: str = ""
    playwright_state_dir: Path = PROJECT_ROOT / "data" / "state"

    # ── Etimad API (tenders) ─────────────────────────────────────────────────
    etimad_client_id: str = ""
    etimad_client_secret: str = ""

    # ── Email (weekly brief delivery) ─────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "brief@whitestar.local"
    # Comma-separated list: "karol@example.com,partner@example.com"
    brief_recipients: str = ""

    def get_brief_recipients(self) -> list[str]:
        """Return list of brief recipient email addresses."""
        return [r.strip() for r in self.brief_recipients.split(",") if r.strip()]

    # ── Auth ─────────────────────────────────────────────────────────────────
    # Single local user seeded by the admin migration
    admin_email: str = "admin@local"
    admin_password: str = "change-me-immediately"

    # ── Spatial / mapping ─────────────────────────────────────────────────────
    # OpenRouteService API key — required for isochrone computation
    ors_api_key: str = ""
    # Drive-time intervals to compute (minutes)
    ors_isochrone_minutes: list[int] = [15, 30, 60]

    # ── Test / golden set ────────────────────────────────────────────────────
    golden_set_dir: Path = PROJECT_ROOT / "backend" / "tests" / "golden"
    # Separate test DB so `make test` never touches production data.
    # Must exist before running tests: createdb wsre_test
    test_database_url: PostgresDsn = PostgresDsn(  # type: ignore[assignment]
        "postgresql+asyncpg://wsuser:wspass@localhost:5432/wsre_test"
    )

    def get_redis_url(self) -> str:
        """Return Redis URL with password injected if configured."""
        if self.redis_password and "://:@" not in self.redis_url and "@" not in self.redis_url:
            return self.redis_url.replace("redis://", f"redis://:{self.redis_password}@")
        return self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
