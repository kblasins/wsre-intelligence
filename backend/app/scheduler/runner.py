"""APScheduler 4 scheduler with SQLAlchemy data store.

Uses Postgres as the job state store so jobs survive restarts and multiple
scheduler processes don't double-fire (transactional locking built in).

Schedule (all times UTC, Saudi business week is Sun-Thu):
  - Tadawul prices:     06:30 UTC Sun-Thu (after Tadawul pre-open)
  - REGA indicators:    04:00 UTC daily
  - Aqar listings:      every 6h
  - MODON news:         08:00 UTC daily
  - News (Argaam):      every 2h during Saudi business hours
  - Outbox reconciler:  every 15min
  - Weekly brief:       06:00 UTC Sunday (markets closed, briefing lands Sunday morning Riyadh)
  - fact_resolved refresh: 05:00 UTC Sunday (before brief)
"""

from __future__ import annotations

import structlog
from apscheduler import AsyncScheduler
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.eventbrokers.redis import RedisEventBroker
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

log = structlog.get_logger(__name__)

# Lazy singleton — initialized in get_scheduler()
_scheduler: AsyncScheduler | None = None


async def get_scheduler() -> AsyncScheduler:
    """Return the module-level scheduler instance, creating it if needed."""
    global _scheduler
    if _scheduler is None:
        # Build a sync URL for APScheduler's SQLAlchemy data store
        raw = str(settings.database_url)
        sync_url = raw.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1).replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

        _scheduler = AsyncScheduler(
            data_store=SQLAlchemyDataStore(sync_url),
            event_broker=RedisEventBroker(str(settings.redis_url)),
        )
    return _scheduler


async def register_jobs(scheduler: AsyncScheduler) -> None:
    """Register all recurring jobs. Idempotent — uses stable job IDs."""
    jobs = [
        # ── Market data ──────────────────────────────────────────────────────
        {
            "func": "app.ingestion.scrapers.tadawul:run_tadawul_scraper",
            "trigger": CronTrigger(
                day_of_week="sun,mon,tue,wed,thu",
                hour=6,
                minute=30,
                timezone="UTC",
            ),
            "id": "tadawul_daily",
            "name": "Tadawul REIT prices (yfinance)",
        },
        {
            "func": "app.ingestion.scrapers.rega:run_rega_scraper",
            "trigger": CronTrigger(hour=4, timezone="UTC"),
            "id": "rega_daily",
            "name": "REGA indicator data",
        },
        {
            "func": "app.ingestion.scrapers.aqar:run_aqar_scraper",
            "trigger": IntervalTrigger(hours=6),
            "id": "aqar_6h",
            "name": "Aqar warehouse listings",
        },
        {
            "func": "app.ingestion.scrapers.modon:run_modon_scraper",
            "trigger": CronTrigger(hour=8, timezone="UTC"),
            "id": "modon_daily",
            "name": "MODON press releases",
        },
        {
            "func": "app.ingestion.scrapers.news:run_news_scraper",
            "trigger": IntervalTrigger(hours=2),
            "id": "news_2h",
            "name": "Argaam / news feed",
        },
        {
            "func": "app.ingestion.scrapers.etimad:run_etimad_scraper",
            "trigger": CronTrigger(hour=7, minute=30, timezone="UTC"),  # daily 10:30 Riyadh
            "id": "etimad_daily",
            "name": "Etimad government tenders",
        },
        # ── Article body fetching ─────────────────────────────────────────────
        {
            "func": "app.ingestion.scrapers.news_body:run_news_body_fetcher",
            "trigger": IntervalTrigger(hours=2),
            "id": "news_body_2h",
            "name": "Fetch full article bodies for high-relevance articles",
        },
        # ── LLM enrichment ───────────────────────────────────────────────────
        {
            "func": "app.ingestion.extractors.news:run_news_extractor",
            "trigger": IntervalTrigger(hours=4),
            "id": "news_extractor_4h",
            "name": "News triage (Haiku 4.5) + extraction (Sonnet 4.6)",
        },
        # ── Structuring sweeps ───────────────────────────────────────────────
        {
            "func": "app.structuring.news:run_news_promotion_sweep",
            "trigger": IntervalTrigger(hours=6),
            "id": "news_promotion_sweep_6h",
            "name": "Promote news rent movements into RentIndex",
        },
        # ── Pipeline ops ─────────────────────────────────────────────────────
        {
            "func": "app.ingestion.reconciler:run_outbox_reconciler",
            "trigger": IntervalTrigger(minutes=15),
            "id": "outbox_reconciler_15m",
            "name": "Outbox reconciler — re-runs extraction for pending blobs",
        },
        {
            "func": "app.scheduler.jobs:refresh_fact_resolved",
            "trigger": CronTrigger(day_of_week="sun", hour=5, timezone="UTC"),
            "id": "fact_resolved_refresh_weekly",
            "name": "Refresh fact_resolved materialized view",
        },
        # ── Weekly brief ─────────────────────────────────────────────────────
        {
            "func": "app.briefing.orchestrator:run_weekly_brief",
            "trigger": CronTrigger(day_of_week="sun", hour=6, timezone="UTC"),
            "id": "weekly_brief_sunday",
            "name": "Weekly briefing — Opus 4.6 synthesis + PDF + email",
        },
        # ── Cost monitoring ──────────────────────────────────────────────────
        {
            "func": "app.scheduler.jobs:check_llm_budget",
            "trigger": IntervalTrigger(hours=1),
            "id": "llm_budget_check_hourly",
            "name": "LLM daily budget gate",
        },
    ]

    existing_ids = {j.id for j in await scheduler.get_jobs()}

    for job_def in jobs:
        if job_def["id"] in existing_ids:
            log.debug("scheduler_job_exists", job_id=job_def["id"])
            continue

        await scheduler.add_schedule(
            job_def["func"],
            job_def["trigger"],
            id=job_def["id"],
        )
        log.info("scheduler_job_registered", job_id=job_def["id"], name=job_def["name"])
