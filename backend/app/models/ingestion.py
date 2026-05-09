"""Models supporting the ingestion pipeline.

raw_ingest_outbox: the transactional link between a raw blob in Object Storage
    and the structured rows it produced. The reconciler job walks this table
    and re-runs extraction for any row where structured=0 (the blob exists but
    extraction crashed before committing).

source_registry: one row per data source, carries last-successful-fetch timestamp
    used for the >48h alerting rule.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class RawIngestOutbox(Base):
    """Outbox table that tracks every raw blob → structured-row transition.

    A reconciler job runs every 15 minutes and processes any row where
    structured_at IS NULL (blob uploaded but extraction not yet committed).

    The outbox enables crash-safe dual writes: raw blob upload and structured
    row insertion happen in the same DB transaction via the outbox record,
    so there is no window where the blob exists but the DB doesn't know about it.
    """

    __tablename__ = "raw_ingest_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha1: Mapped[str] = mapped_column(String(40), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/html")
    # 0 = pending extraction, 1 = extraction committed
    structured: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    structured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Extraction error, if any — allows inspecting why a blob failed
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Metadata forwarded from the scraper
    scraper_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SourceRegistry(Base):
    """One row per data source — tracks health and last-fetch cadence.

    The >48h staleness alert fires when `last_success_at` hasn't advanced.
    """

    __tablename__ = "source_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "scraper", "api", "pdf", "feed"
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Priority used in fact_resolved view conflict resolution (1=highest)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
