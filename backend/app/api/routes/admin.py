"""Admin / ops endpoints — internal dashboard use only.

Not auth-gated in local mode (no external exposure). Covers:
  - LLM budget status
  - Review queue summary + mark-reviewed
  - Outbox pipeline health
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.database import get_db_session
from app.models.ingestion import RawIngestOutbox, SourceRegistry
from app.models.llm import LLMCall
from app.models.market import MacroIndicator, NewsArticle
from app.models.review import ReviewQueue

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/budget")
async def get_budget_status(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """LLM spend summary: today, yesterday, this week, all time."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    async def _spend(since: datetime, until: datetime | None = None) -> float:
        stmt = select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(
            LLMCall.called_at >= since
        )
        if until:
            stmt = stmt.where(LLMCall.called_at < until)
        result = await session.execute(stmt)
        return float(result.scalar_one())

    async def _calls(since: datetime) -> int:
        result = await session.execute(
            select(func.count()).select_from(LLMCall).where(LLMCall.called_at >= since)
        )
        return result.scalar_one() or 0

    # Per-model breakdown today
    model_rows = (
        await session.execute(
            select(LLMCall.model_id, func.sum(LLMCall.cost_usd).label("spend"))
            .where(LLMCall.called_at >= today_start)
            .group_by(LLMCall.model_id)
        )
    ).all()

    from app.core.config import settings

    today_usd = await _spend(today_start)
    return {
        "today_usd": round(today_usd, 4),
        "yesterday_usd": round(await _spend(yesterday_start, today_start), 4),
        "week_usd": round(await _spend(week_start), 4),
        "alltime_usd": round(await _spend(datetime(2024, 1, 1, tzinfo=UTC)), 4),
        "today_calls": await _calls(today_start),
        "daily_cap_usd": settings.claude_daily_budget_usd,
        "budget_pct": round(today_usd / settings.claude_daily_budget_usd * 100, 1),
        "models": {row.model_id: round(float(row.spend), 4) for row in model_rows},
    }


@router.get("/pipeline")
async def get_pipeline_status(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Outbox and review queue health check."""
    # Outbox: pending vs failed vs done
    outbox_rows = (
        await session.execute(
            select(
                RawIngestOutbox.structured,
                func.count().label("n"),
            ).group_by(RawIngestOutbox.structured)
        )
    ).all()
    outbox = {r.structured: r.n for r in outbox_rows}

    failed_rows = (
        await session.execute(
            select(func.count())
            .select_from(RawIngestOutbox)
            .where(RawIngestOutbox.retry_count >= 3, RawIngestOutbox.structured == 0)
        )
    ).scalar_one()

    # Review queue
    rq_total = (await session.execute(select(func.count()).select_from(ReviewQueue))).scalar_one()
    rq_pending = (
        await session.execute(
            select(func.count()).select_from(ReviewQueue).where(ReviewQueue.reviewed_at.is_(None))
        )
    ).scalar_one()

    # News backlogs
    triage_backlog = (
        await session.execute(
            select(func.count())
            .select_from(NewsArticle)
            .where(NewsArticle.relevance_score.is_(None))
        )
    ).scalar_one()

    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    extraction_backlog = (
        await session.execute(
            select(func.count())
            .select_from(NewsArticle)
            .where(
                NewsArticle.relevance_score >= 0.5,
                NewsArticle.structured_facts == cast("{}", JSONB),
            )
        )
    ).scalar_one()

    body_fetching_backlog = (
        await session.execute(
            select(func.count())
            .select_from(NewsArticle)
            .where(
                NewsArticle.relevance_score >= 0.5,
                NewsArticle.body_en.is_(None),
                NewsArticle.body_ar.is_(None),
                NewsArticle.url.is_not(None),
            )
        )
    ).scalar_one()

    return {
        "outbox": {
            "pending": outbox.get(0, 0),
            "done": outbox.get(1, 0),
            "permanently_failed": int(failed_rows),
        },
        "review_queue": {
            "total": int(rq_total),
            "pending_review": int(rq_pending),
        },
        "news": {
            "triage_backlog": int(triage_backlog),
            "extraction_backlog": int(extraction_backlog),
            "body_fetching_backlog": int(body_fetching_backlog),
        },
    }


@router.get("/review-queue")
async def list_review_queue(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    pending_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    """Items in the human review queue (confidence ≤ 3 extractions)."""
    stmt = select(ReviewQueue).order_by(ReviewQueue.created_at.desc()).limit(limit)
    if pending_only:
        stmt = stmt.where(ReviewQueue.reviewed_at.is_(None))

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "source_table": r.source_table,
            "source_row_id": r.source_row_id,
            "confidence": r.confidence,
            "uncertain_fields": r.uncertain_fields,
            "llm_output": r.llm_output,
            "model_id": r.model_id,
            "is_golden": r.is_golden,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.patch("/review-queue/{item_id}")
async def resolve_review_item(
    item_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    is_golden: bool = False,
) -> dict:
    """Mark a review queue item as reviewed.

    Set is_golden=true to add it to the regression test golden set.
    """
    result = await session.execute(select(ReviewQueue).where(ReviewQueue.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")

    await session.execute(
        update(ReviewQueue)
        .where(ReviewQueue.id == item_id)
        .values(reviewed_at=datetime.now(UTC), is_golden=is_golden)
    )
    return {"id": item_id, "reviewed": True, "is_golden": is_golden}


@router.get("/jobs")
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """Scraper / job health from source_registry — last run, success, staleness."""
    now = datetime.now(UTC)
    rows = (
        (await session.execute(select(SourceRegistry).order_by(SourceRegistry.source_key)))
        .scalars()
        .all()
    )
    result = []
    for r in rows:
        age_hours: float | None = None
        if r.last_success_at:
            age_hours = round((now - r.last_success_at).total_seconds() / 3600, 1)
        result.append(
            {
                "source_key": r.source_key,
                "display_name": r.display_name,
                "source_type": r.source_type,
                "is_enabled": r.is_enabled,
                "last_attempt_at": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
                "last_success_at": r.last_success_at.isoformat() if r.last_success_at else None,
                "age_hours": age_hours,
                "consecutive_failures": r.consecutive_failures,
                "stale": age_hours is not None and age_hours > 48,
            }
        )
    return result


@router.patch("/sources/{source_key}")
async def toggle_source(
    source_key: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    enabled: bool = True,
) -> dict:
    """Enable or disable a data source in the source registry.

    Disabled sources are skipped by the scheduler and show as
    'disabled' in the Jobs table (not counted as stale).
    """
    result = await session.execute(
        select(SourceRegistry).where(SourceRegistry.source_key == source_key)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_key}' not found")

    await session.execute(
        update(SourceRegistry)
        .where(SourceRegistry.source_key == source_key)
        .values(is_enabled=enabled)
    )
    await session.commit()
    return {"source_key": source_key, "is_enabled": enabled}


@router.get("/outbox/failed")
async def list_failed_outbox(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = 50,
) -> list[dict]:
    """Permanently failed outbox rows (retry_count >= 3, structured = 0).

    Useful for diagnosing extraction errors without reading raw logs.
    """
    rows = (
        (
            await session.execute(
                select(RawIngestOutbox)
                .where(RawIngestOutbox.retry_count >= 3, RawIngestOutbox.structured == 0)
                .order_by(RawIngestOutbox.fetched_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "source": r.source,
            "raw_uri": r.raw_uri,
            "retry_count": r.retry_count,
            "extraction_error": r.extraction_error,
            "fetched_at": r.fetched_at.isoformat(),
        }
        for r in rows
    ]


# Known scraper module paths keyed by source_key
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


@router.post("/scraper/{source_key}/trigger")
async def trigger_scraper(
    source_key: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Manually trigger a scraper run in the background.

    Useful for testing or forcing a refresh without waiting for the scheduler.
    Only works for scrapers with a registered module.
    """
    import asyncio
    import importlib

    if source_key not in _SCRAPER_MODULES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source_key '{source_key}'. Known: {sorted(_SCRAPER_MODULES)}",
        )

    module_path = _SCRAPER_MODULES[source_key]

    async def _run() -> None:
        from app.core.database import AsyncSessionFactory

        mod = importlib.import_module(module_path)
        # Find the scraper class — convention: subclass of BaseScraper
        from app.ingestion.base import BaseScraper

        for attr in dir(mod):
            cls = getattr(mod, attr)
            try:
                if (
                    isinstance(cls, type)
                    and issubclass(cls, BaseScraper)
                    and cls is not BaseScraper
                ):
                    async with AsyncSessionFactory() as session:
                        scraper = cls(session)
                        await scraper.scrape(session)
                    return
            except Exception:
                continue

    background_tasks.add_task(asyncio.ensure_future, _run())
    return {"status": "triggered", "source_key": source_key}


# Pipeline step triggers — for background processing stages (not scrapers)
_PIPELINE_STEPS: dict[str, str] = {
    "news_body": "app.ingestion.scrapers.news_body:run_news_body_fetcher",
    "news_extract": "app.ingestion.extractors.news:run_news_extractor",
}


@router.post("/pipeline/{step}/trigger")
async def trigger_pipeline_step(
    step: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Manually trigger a pipeline processing step (body fetch, LLM extraction).

    Useful for re-running a stuck stage without waiting for the scheduler.
    """
    import asyncio
    import importlib

    if step not in _PIPELINE_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown step '{step}'. Known: {sorted(_PIPELINE_STEPS)}",
        )

    module_path, func_name = _PIPELINE_STEPS[step].rsplit(":", 1)

    async def _run() -> None:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, func_name)
        await fn()

    background_tasks.add_task(asyncio.ensure_future, _run())
    return {"status": "triggered", "step": step}


@router.post("/rent-index/import")
async def import_rent_index_csv(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile,
    source: str = "manual_import",
    source_priority: int = 2,
) -> dict:
    """Import rent index rows from a CSV file.

    Expected columns (required): district, property_type, period, rent_sar_sqm_annual
    Optional columns: city, yoy_change_pct, vacancy_pct

    Returns counts of rows inserted vs skipped (upsert by unique constraint).
    """
    import csv
    import io

    from app.models.market import RentIndex

    try:
        content = await file.read()
        text = content.decode("utf-8-sig")  # handle BOM
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))
    required = {"district", "property_type", "period", "rent_sar_sqm_annual"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=422,
            detail=f"CSV must have columns: {sorted(required)}. Got: {reader.fieldnames}",
        )

    inserted = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        try:
            rent_val = float(row["rent_sar_sqm_annual"])
        except (ValueError, KeyError):
            errors.append(
                f"Row {i}: invalid rent_sar_sqm_annual '{row.get('rent_sar_sqm_annual')}'"
            )
            skipped += 1
            continue

        now = datetime.now(UTC)
        entry = RentIndex(
            district=row.get("district") or None,
            city=row.get("city") or "Riyadh",
            property_type=row["property_type"].strip(),
            period=row["period"].strip(),
            rent_sar_sqm_annual=rent_val,
            yoy_change_pct=float(row["yoy_change_pct"]) if row.get("yoy_change_pct") else None,
            vacancy_pct=float(row["vacancy_pct"]) if row.get("vacancy_pct") else None,
            source=source,
            source_priority=source_priority,
            extracted_at=now,
        )
        session.add(entry)
        try:
            await session.flush()
            inserted += 1
        except Exception:
            await session.rollback()
            skipped += 1

    await session.commit()
    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors[:10],  # cap at 10 errors in response
    }


@router.get("/health")
async def admin_health(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Single-call health summary for external monitoring / uptime checks.

    Returns HTTP 200 with overall status. If any critical check fails,
    `status` is "degraded" but the response is still 200 (not 503),
    so that the dashboard can show a degraded state gracefully.
    """
    from sqlalchemy import func

    from app.ingestion.circuit_breakers import BREAKERS

    # Check DB is reachable
    try:
        await session.execute(select(func.count()).select_from(LLMCall))
        db_ok = True
    except Exception:
        db_ok = False

    # Count open breakers
    open_breakers = [
        name for name, cb in BREAKERS.items() if getattr(cb, "current_state", "closed") != "closed"
    ]

    # Pending review items
    rq_pending = (
        await session.execute(
            select(func.count()).select_from(ReviewQueue).where(ReviewQueue.reviewed_at.is_(None))
        )
    ).scalar_one()

    overall = "ok" if db_ok and not open_breakers else "degraded"

    return {
        "status": overall,
        "db": "ok" if db_ok else "error",
        "open_circuit_breakers": open_breakers,
        "review_queue_pending": int(rq_pending),
    }


@router.get("/llm-calls")
async def list_llm_calls(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = 100,
    task_type: str | None = None,
    model_id: str | None = None,
) -> list[dict]:
    """Recent LLM calls with cost, tokens, and task context.

    Useful for diagnosing cost spikes and verifying prompt caching is working.
    """
    stmt = select(LLMCall).order_by(LLMCall.called_at.desc()).limit(min(limit, 500))
    if task_type:
        stmt = stmt.where(LLMCall.task_type == task_type)
    if model_id:
        stmt = stmt.where(LLMCall.model_id == model_id)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "model_id": r.model_id,
            "task_type": r.task_type,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cache_read_tokens": r.cache_read_tokens,
            "cache_write_tokens": r.cache_write_tokens,
            "cost_usd": float(r.cost_usd),
            "is_batch": r.is_batch,
            "success": r.success,
            "called_at": r.called_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/budget/by-task")
async def budget_by_task(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = 7,
) -> list[dict]:
    """LLM spend grouped by task_type for the last N days.

    Useful for identifying which pipeline stage is consuming the most budget.
    """
    from sqlalchemy import func

    now = datetime.now(UTC)
    since = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        await session.execute(
            select(
                LLMCall.task_type,
                func.count().label("calls"),
                func.sum(LLMCall.cost_usd).label("spend"),
                func.sum(LLMCall.input_tokens).label("input_tokens"),
                func.sum(LLMCall.output_tokens).label("output_tokens"),
                func.sum(LLMCall.cache_read_tokens).label("cache_read_tokens"),
            )
            .select_from(LLMCall)
            .where(LLMCall.called_at >= since)
            .group_by(LLMCall.task_type)
            .order_by(func.sum(LLMCall.cost_usd).desc())
        )
    ).all()

    return [
        {
            "task_type": r.task_type,
            "calls": r.calls,
            "spend_usd": round(float(r.spend), 4),
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cache_read_tokens": r.cache_read_tokens,
        }
        for r in rows
    ]


@router.get("/budget/history")
async def get_budget_history(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = 14,
) -> list[dict]:
    """Daily LLM spend for the last N days (default 14).

    Returns one entry per calendar day. Days with zero spend are included.
    """
    from sqlalchemy import func

    now = datetime.now(UTC)
    since = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

    day_trunc = func.date_trunc("day", LLMCall.called_at)
    day_label = func.to_char(day_trunc, "YYYY-MM-DD").label("day")

    rows = (
        await session.execute(
            select(
                day_label,
                func.sum(LLMCall.cost_usd).label("spend"),
                func.count().label("calls"),
            )
            .select_from(LLMCall)
            .where(LLMCall.called_at >= since)
            .group_by(day_trunc)
            .order_by(day_trunc)
        )
    ).all()

    return [
        {
            "day": r.day,
            "spend_usd": round(float(r.spend), 4),
            "calls": r.calls,
        }
        for r in rows
    ]


@router.get("/districts")
async def list_district_aliases(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    city: str | None = None,
) -> list[dict]:
    """All district aliases grouped by canonical_id.

    Each entry shows the canonical EN/AR name plus every known alias spelling.
    Used to audit the normalization table and spot missing mappings.
    """
    from app.models.market import DistrictAlias

    stmt = select(DistrictAlias).order_by(
        DistrictAlias.canonical_id, DistrictAlias.alias_lang, DistrictAlias.alias
    )
    if city:
        stmt = stmt.where(DistrictAlias.city.ilike(f"%{city}%"))

    rows = (await session.execute(stmt)).scalars().all()

    # Group by canonical_id
    groups: dict[int, dict] = {}
    for r in rows:
        if r.canonical_id not in groups:
            groups[r.canonical_id] = {
                "canonical_id": r.canonical_id,
                "name_en": r.name_en,
                "name_ar": r.name_ar,
                "city": r.city,
                "aliases": [],
            }
        groups[r.canonical_id]["aliases"].append(
            {
                "alias": r.alias,
                "lang": r.alias_lang,
                "source": r.source,
            }
        )

    return list(groups.values())


class DistrictAliasCreate(BaseModel):
    canonical_id: int
    alias: str
    lang: str = "en"
    source: str | None = None
    name_en: str | None = None
    name_ar: str | None = None
    city: str = "Riyadh"


@router.post("/districts")
async def create_district_alias(
    body: DistrictAliasCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Add a new alias mapping for an existing canonical district.

    Useful when a new data source uses a spelling not yet in the registry.
    """
    from app.models.market import DistrictAlias

    row = DistrictAlias(
        canonical_id=body.canonical_id,
        alias=body.alias.strip(),
        alias_lang=body.lang,
        source=body.source,
        name_en=body.name_en,
        name_ar=body.name_ar,
        city=body.city,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "canonical_id": row.canonical_id,
        "alias": row.alias,
        "alias_lang": row.alias_lang,
    }


@router.get("/circuit-breakers")
async def get_circuit_breaker_status() -> list[dict]:
    """State of all registered circuit breakers.

    Returns open/closed/half-open state, failure count, and thresholds
    for every source-level breaker. Useful for diagnosing stuck scrapers.
    """
    from app.ingestion.circuit_breakers import BREAKERS

    result = []
    for name, cb in sorted(BREAKERS.items()):
        try:
            state = cb.current_state
        except Exception:
            state = "unknown"
        result.append(
            {
                "name": name,
                "state": state,
                "fail_counter": cb.fail_counter,
                "fail_max": cb.fail_max,
                "reset_timeout_s": cb.reset_timeout,
            }
        )
    return result


@router.get("/schedule")
async def get_schedule() -> list[dict]:
    """Next-fire times for all registered scheduler jobs.

    Returns an empty list when the scheduler is not running (e.g. during tests).
    """
    from app.core.scheduler import scheduler

    if scheduler is None:
        return []

    schedules = await scheduler.get_schedules()
    now = datetime.now(UTC)
    result = []
    for sched in schedules:
        next_fire = sched.next_fire_time
        result.append(
            {
                "id": sched.id,
                "next_fire_time": next_fire.isoformat() if next_fire else None,
                "minutes_until": (
                    round((next_fire - now).total_seconds() / 60, 1) if next_fire else None
                ),
            }
        )
    return sorted(result, key=lambda r: r["next_fire_time"] or "")


_VALID_MACRO_KEYS = frozenset({
    # Saudi macro keys
    "sama_repo_rate",
    "sar_usd",
    "brent",
    "saudi_10y_yield",
    "riyadh_population",
    # Polish / Warsaw macro keys (WS4)
    "nbp_reference_rate",
    "eur_pln",
    "pln_10y_yield",
    "cpi_yoy",
    "unemployment_rate",
    "pmi_construction",
    "avg_mortgage_rate",
    "gdp_yoy",
    "warsaw_prime_office_yield",
    "warsaw_office_q1_net_absorption_sqm",
    "warsaw_ytd_investment_volume_meur",
})


class MacroIndicatorUpdate(BaseModel):
    value: float
    period: str                    # e.g. "2026-Q1" or "2026-04"
    source: str = "manual"
    source_url: str | None = None


@router.get("/macro-indicators")
async def get_macro_indicators(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """All current macro indicator values."""
    rows = (await session.execute(select(MacroIndicator).order_by(MacroIndicator.indicator_key))).scalars().all()
    return [
        {
            "key": r.indicator_key,
            "value": float(r.value),
            "period": r.period,
            "source": r.source,
            "source_url": r.source_url,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


@router.post("/macro-indicators/{key}")
async def update_macro_indicator(
    key: str,
    body: MacroIndicatorUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Upsert a single macro indicator value (admin-only, manual update).

    Valid keys: sama_repo_rate, sar_usd, brent, saudi_10y_yield, cpi_yoy,
                riyadh_population
    """
    if key not in _VALID_MACRO_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown indicator key '{key}'. Valid keys: {sorted(_VALID_MACRO_KEYS)}",
        )

    now = datetime.now(UTC)
    existing = await session.get(MacroIndicator, key)
    if existing is None:
        row = MacroIndicator(
            indicator_key=key,
            value=body.value,
            period=body.period,
            source=body.source,
            source_url=body.source_url,
            fetched_at=now,
        )
        session.add(row)
    else:
        existing.value = body.value  # type: ignore[assignment]
        existing.period = body.period
        existing.source = body.source
        existing.source_url = body.source_url
        existing.fetched_at = now

    await session.commit()
    return {
        "key": key,
        "value": body.value,
        "period": body.period,
        "source": body.source,
        "fetched_at": now.isoformat(),
    }
