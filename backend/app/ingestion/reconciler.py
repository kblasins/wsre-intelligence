"""Outbox reconciler — re-runs extraction for blobs with pending status.

Runs every 15 minutes. Looks for raw_ingest_outbox rows where:
  - structured = 0  (extraction not yet committed)
  - retry_count < 3 (not permanently failed)
  - fetched_at < now() - 5min  (give the initial extraction time to commit)

For each pending row, downloads the blob from Object Storage and re-runs
the appropriate extractor. On success, marks structured=1. On failure,
increments retry_count and records the error.

After retry_count reaches 3, the row is left in place for manual review
— it shows up in the admin UI with the extraction_error.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, update

from app.core.database import AsyncSessionFactory
from app.core.storage import download_raw
from app.models.ingestion import RawIngestOutbox

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

MAX_RETRIES = 3
GRACE_PERIOD = timedelta(minutes=5)


async def run_outbox_reconciler() -> None:
    """Entry point called by APScheduler every 15 minutes."""
    async with AsyncSessionFactory() as session:
        pending = await _get_pending_rows(session)
        if not pending:
            return

        log.info("reconciler_start", pending_count=len(pending))
        success = 0
        failed = 0

        for row in pending:
            try:
                await _process_row(session, row)
                success += 1
            except Exception as exc:
                failed += 1
                log.warning("reconciler_row_failed", outbox_id=row.id, error=str(exc))
                await _mark_failed(session, row.id, str(exc))

        log.info("reconciler_done", success=success, failed=failed)


async def _get_pending_rows(session: AsyncSession) -> list[RawIngestOutbox]:
    cutoff = datetime.now(UTC) - GRACE_PERIOD
    result = await session.execute(
        select(RawIngestOutbox)
        .where(
            RawIngestOutbox.structured == 0,
            RawIngestOutbox.retry_count < MAX_RETRIES,
            RawIngestOutbox.fetched_at < cutoff,
        )
        .order_by(RawIngestOutbox.fetched_at)
        .limit(50)
    )
    return list(result.scalars())


async def _process_row(session: AsyncSession, row: RawIngestOutbox) -> None:
    """Download the blob and re-run extraction for one outbox row."""
    log.info("reconciler_processing", outbox_id=row.id, source=row.source, uri=row.raw_uri)

    raw_bytes = download_raw(row.raw_uri)

    # Dispatch to the appropriate extractor based on source
    extractor = _get_extractor(row.source)
    if extractor is None:
        raise ValueError(f"No extractor registered for source: {row.source}")

    await extractor(session, raw_bytes, row)

    # Mark as successfully structured
    await session.execute(
        update(RawIngestOutbox)
        .where(RawIngestOutbox.id == row.id)
        .values(structured=1, structured_at=datetime.now(UTC))
    )
    await session.commit()


async def _mark_failed(session: AsyncSession, row_id: int, error: str) -> None:
    await session.execute(
        update(RawIngestOutbox)
        .where(RawIngestOutbox.id == row_id)
        .values(
            retry_count=RawIngestOutbox.retry_count + 1,
            extraction_error=error[:2000],
        )
    )
    await session.commit()


def _get_extractor(source: str):  # type: ignore[return]
    """Return the extraction coroutine for a given source key.

    Import is deferred to avoid circular imports at module load time.
    """
    _scraper_modules = {
        "tadawul": "app.ingestion.scrapers.tadawul",
        "aqar": "app.ingestion.scrapers.aqar",
        "news": "app.ingestion.scrapers.news",
        "argaam_en": "app.ingestion.scrapers.news",
        "argaam_ar": "app.ingestion.scrapers.news",
        "saudi_gazette": "app.ingestion.scrapers.news",
        "arab_news": "app.ingestion.scrapers.news",
        "modon": "app.ingestion.scrapers.modon",
        "rega": "app.ingestion.scrapers.rega",
        # PDFs go through the LLM extractor, not the scraper's extract_from_blob
        "knight_frank": "app.pdf.extractor",
        "cbre": "app.pdf.extractor",
        "jll": "app.pdf.extractor",
        # Etimad government tenders
        "etimad": "app.ingestion.scrapers.etimad",
    }

    module_path = _scraper_modules.get(source)
    if module_path is None:
        return None

    try:
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, "extract_from_blob", None)
    except ImportError:
        return None
