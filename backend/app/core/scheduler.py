"""Background scheduler — runs scrapers and briefing pipeline on a fixed cadence.

Uses APScheduler 4.x AsyncScheduler with in-memory job store (no external broker
required for local operation). Jobs are re-registered each startup.

Schedule (all times Asia/Riyadh, UTC+3):
  - REIT snapshots:    every 6h
  - News scrapers:     every 4h
  - News body fetcher: every 2h (after triage)
  - News extractor:    every 2h (after body fetch)
  - Listings (Aqar):   every 12h
  - Tenders (Etimad):  every 24h (09:00)
  - REGA transactions: every 24h (07:00)
  - Weekly brief:      Sunday 08:00 (week_ending = Saturday)
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = structlog.get_logger(__name__)

# Module path for each source key (mirrors admin.py _SCRAPER_MODULES)
_SCRAPER_MODULES: dict[str, str] = {
    "tadawul": "app.ingestion.scrapers.tadawul",
    "rega": "app.ingestion.scrapers.rega",
    "aqar": "app.ingestion.scrapers.aqar",
    "modon": "app.ingestion.scrapers.modon",
    "argaam_en": "app.ingestion.scrapers.news",
    "argaam_ar": "app.ingestion.scrapers.news",
    "saudi_gazette": "app.ingestion.scrapers.news",
    "arab_news": "app.ingestion.scrapers.news",
    "etimad": "app.ingestion.scrapers.etimad",
}


async def _run_scraper(source_key: str) -> None:
    """Dynamically load and run a scraper by source_key."""
    from app.core.database import AsyncSessionFactory
    from app.ingestion.base import BaseScraper

    module_path = _SCRAPER_MODULES.get(source_key)
    if not module_path:
        log.warning("scheduler_unknown_source", source_key=source_key)
        return

    try:
        mod = importlib.import_module(module_path)
        for attr in dir(mod):
            cls = getattr(mod, attr)
            try:
                if (
                    isinstance(cls, type)
                    and issubclass(cls, BaseScraper)
                    and cls is not BaseScraper
                ):
                    log.info("scheduler_scraper_start", source_key=source_key)
                    async with AsyncSessionFactory() as session:
                        scraper = cls(session)
                        await scraper.scrape(session)
                    log.info("scheduler_scraper_done", source_key=source_key)
                    return
            except Exception:
                continue
        log.warning("scheduler_no_scraper_found", source_key=source_key)
    except Exception:
        log.exception("scheduler_scraper_error", source_key=source_key)


async def _run_news_body_fetcher() -> None:
    """Fetch full body text for high-relevance articles."""
    try:
        log.info("scheduler_news_body_start")
        from app.ingestion.scrapers.news_body import run_news_body_fetcher

        await run_news_body_fetcher()
        log.info("scheduler_news_body_done")
    except Exception:
        log.exception("scheduler_news_body_error")


async def _run_news_extractor() -> None:
    """Run LLM extraction on body-fetched articles."""
    try:
        log.info("scheduler_news_extract_start")
        from app.ingestion.extractors.news import run_news_extractor

        await run_news_extractor()
        log.info("scheduler_news_extract_done")
    except Exception:
        log.exception("scheduler_news_extract_error")


async def _run_district_velocity_refresh() -> None:
    """Refresh district_velocity materialized view."""
    try:
        log.info("scheduler_district_velocity_start")
        from app.scheduler.jobs import refresh_district_velocity

        await refresh_district_velocity()
        log.info("scheduler_district_velocity_done")
    except Exception:
        log.exception("scheduler_district_velocity_error")


async def _run_overpass_refresh() -> None:
    """Refresh POIs from OpenStreetMap Overpass API (Sunday 02:00 UTC)."""
    try:
        log.info("scheduler_overpass_start")
        from app.ingestion.scrapers.overpass import run_overpass_refresh

        await run_overpass_refresh()
        log.info("scheduler_overpass_done")
    except Exception:
        log.exception("scheduler_overpass_error")


async def _run_fact_resolved_refresh() -> None:
    """Refresh the fact_resolved materialized view."""
    try:
        log.info("scheduler_fact_resolved_start")
        from app.scheduler.jobs import refresh_fact_resolved

        await refresh_fact_resolved()
        log.info("scheduler_fact_resolved_done")
    except Exception:
        log.exception("scheduler_fact_resolved_error")


async def _run_weekly_brief() -> None:
    """Generate the weekly brief for the most recently completed Saturday."""
    from app.briefing.orchestrator import run_weekly_brief

    now = datetime.now(UTC)
    # Find most recent Saturday (weekday 5)
    days_since_saturday = (now.weekday() - 5) % 7
    week_ending = (now - timedelta(days=days_since_saturday)).date()

    try:
        log.info("scheduler_brief_start", week_ending=str(week_ending))
        await run_weekly_brief(week_ending)
        log.info("scheduler_brief_done", week_ending=str(week_ending))
    except Exception:
        log.exception("scheduler_brief_error", week_ending=str(week_ending))


scheduler: AsyncScheduler | None = None


# Named wrappers for source-keyed scraper jobs.
# APScheduler 4.x cannot serialize lambdas or closures; all scheduled
# callables must be importable top-level functions.
async def _run_tadawul() -> None:
    await _run_scraper("tadawul")


async def _run_argaam_en() -> None:
    await _run_scraper("argaam_en")


async def _run_argaam_ar() -> None:
    await _run_scraper("argaam_ar")


async def _run_saudi_gazette() -> None:
    await _run_scraper("saudi_gazette")


async def _run_arab_news() -> None:
    await _run_scraper("arab_news")


async def _run_modon() -> None:
    await _run_scraper("modon")


async def _run_aqar() -> None:
    await _run_scraper("aqar")


async def _run_etimad() -> None:
    await _run_scraper("etimad")


async def _run_rega() -> None:
    await _run_scraper("rega")


async def start_scheduler() -> AsyncScheduler:
    """Create and start the global scheduler. Call from lifespan startup.

    APScheduler 4.x requires initialization via __aenter__ before any
    other method (add_schedule, start_in_background) can be called.
    """
    global scheduler

    s = AsyncScheduler()
    await s.__aenter__()  # initialize data stores and task group

    # REIT snapshots — every 6 hours
    await s.add_schedule(_run_tadawul, IntervalTrigger(hours=6), id="tadawul")

    # News scrapers — every 4 hours, staggered by 90s each
    news_jobs: list[tuple[str, object]] = [
        ("argaam_en", _run_argaam_en),
        ("argaam_ar", _run_argaam_ar),
        ("saudi_gazette", _run_saudi_gazette),
        ("arab_news", _run_arab_news),
        ("modon", _run_modon),
    ]
    for i, (src_id, fn) in enumerate(news_jobs):
        await s.add_schedule(fn, IntervalTrigger(hours=4, seconds=i * 90), id=f"news_{src_id}")

    # Listings — every 12 hours
    await s.add_schedule(_run_aqar, IntervalTrigger(hours=12), id="aqar")

    # Tenders — daily at 09:00 Riyadh (06:00 UTC)
    await s.add_schedule(
        _run_etimad, CronTrigger(hour=6, minute=0, timezone="UTC"), id="etimad"
    )

    # REGA transactions — daily at 07:00 Riyadh (04:00 UTC)
    await s.add_schedule(
        _run_rega, CronTrigger(hour=4, minute=0, timezone="UTC"), id="rega"
    )

    # News body fetcher — every 2 hours (offset 30min)
    await s.add_schedule(
        _run_news_body_fetcher, IntervalTrigger(hours=2, minutes=30), id="news_body"
    )

    # News LLM extractor — every 2 hours (offset 60min)
    await s.add_schedule(
        _run_news_extractor, IntervalTrigger(hours=2, minutes=60), id="news_extract"
    )

    # POI refresh — Sunday 02:00 UTC
    await s.add_schedule(
        _run_overpass_refresh,
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="UTC"),
        id="overpass_poi",
    )

    # District velocity refresh — Sunday 03:00 UTC
    await s.add_schedule(
        _run_district_velocity_refresh,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="UTC"),
        id="district_velocity",
    )

    # fact_resolved refresh — nightly 04:30 UTC
    await s.add_schedule(
        _run_fact_resolved_refresh,
        CronTrigger(hour=4, minute=30, timezone="UTC"),
        id="fact_resolved",
    )

    # Weekly brief — Sunday 05:00 UTC (08:00 Riyadh)
    await s.add_schedule(
        _run_weekly_brief,
        CronTrigger(day_of_week="sun", hour=5, minute=0, timezone="UTC"),
        id="weekly_brief",
    )

    await s.start_in_background()
    scheduler = s
    job_ids = [
        "tadawul", "aqar", "etimad", "rega",
        "news_body", "news_extract",
        "overpass_poi", "district_velocity", "fact_resolved", "weekly_brief",
        *[f"news_{src}" for src in ["argaam_en", "argaam_ar", "saudi_gazette", "arab_news", "modon"]],
    ]
    log.info("scheduler_started", job_count=len(job_ids))
    return s


async def stop_scheduler() -> None:
    """Gracefully stop the scheduler. Call from lifespan shutdown."""
    global scheduler
    if scheduler is not None:
        await scheduler.__aexit__(None, None, None)
        scheduler = None
        log.info("scheduler_stopped")
