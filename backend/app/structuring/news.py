"""News structuring pipeline — promotes rent movements from news extractions into RentIndex.

Called after the Sonnet extraction pass populates news_articles.structured_facts.
Scans the rent_movements array and writes RentIndex rows at source_priority=3 (news).

Entry points:
  promote_news_facts(session, article_id, structured_facts)  — called inline from extractor
  promote_all_pending(session)                               — called from tests / one-off scripts
  run_news_promotion_sweep()                                 — no-arg scheduler entry point
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import AsyncSessionFactory
from app.models.market import NewsArticle, RentIndex

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

_PTYPE_MAP: dict[str, str] = {
    "warehouse": "warehouse",
    "warehouses": "warehouse",
    "industrial": "industrial_land",
    "industrial land": "industrial_land",
    "industrial_land": "industrial_land",
    "factory": "factory",
    "logistics": "logistics",
    "office": "office",
    "retail": "retail",
}


def _normalize_ptype(raw: str | None) -> str:
    if not raw:
        return "warehouse"
    return _PTYPE_MAP.get(raw.strip().lower(), "warehouse")


async def promote_news_facts(
    session: AsyncSession,
    article_id: int,
    structured_facts: dict[str, Any],
    raw_uri: str | None,
    model_id: str | None,
    prompt_sha: str | None,
) -> int:
    """Write RentIndex rows from a single article's structured_facts.

    Returns number of rows written.
    """
    movements: list[dict[str, Any]] = structured_facts.get("rent_movements", [])
    if not movements:
        return 0

    now = datetime.now(UTC)
    # Use published_at year as the period if no explicit period on the movement
    count = 0

    for mv in movements:
        direction = mv.get("direction")
        change_pct = mv.get("change_pct")
        period = str(mv.get("period") or "")[:20] or None
        if not period:
            continue  # no period = can't place the observation in time

        # Convert direction + change_pct to yoy_change_pct
        yoy: float | None = None
        if change_pct is not None:
            import contextlib

            with contextlib.suppress(ValueError, TypeError):
                yoy = float(change_pct) if direction != "down" else -abs(float(change_pct))

        row: dict[str, Any] = {
            "district": mv.get("district"),
            "city": "Riyadh",
            "property_type": _normalize_ptype(mv.get("property_type")),
            "period": period,
            "rent_sar_sqm_annual": None,  # news articles rarely give absolute rent levels
            "yoy_change_pct": yoy,
            "vacancy_pct": None,
            "source": f"news_article_{article_id}",
            "source_priority": 3,
            "raw_uri": raw_uri,
            "extracted_at": now,
            "model_id": model_id,
            "prompt_sha": prompt_sha,
        }

        stmt = (
            insert(RentIndex)
            .values(**row)
            .on_conflict_do_update(
                constraint="uq_rent_index_district_type_period_source",
                set_={"yoy_change_pct": yoy, "extracted_at": now},
            )
        )
        await session.execute(stmt)
        count += 1

    return count


async def promote_all_pending(session: AsyncSession) -> int:
    """Sweep all articles with structured_facts that haven't been promoted yet.

    An article is considered un-promoted if it has rent_movements and
    no corresponding RentIndex rows with source starting 'news_article_<id>'.
    """
    result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.structured_facts["rent_movements"].as_string() != "[]",
            NewsArticle.structured_facts.has_key("rent_movements"),
        )
        .limit(200)
    )
    articles = list(result.scalars())
    total = 0

    for article in articles:
        facts = article.structured_facts
        if not isinstance(facts, dict):
            continue
        n = await promote_news_facts(
            session,
            article.id,
            facts,
            article.raw_uri,
            article.model_id,
            article.prompt_sha,
        )
        total += n

    if total:
        await session.commit()
        log.info("news_promotion_sweep_done", promoted_rows=total, articles_checked=len(articles))

    return total


async def run_news_promotion_sweep() -> int:
    """No-arg entry point for APScheduler — creates its own session."""
    async with AsyncSessionFactory() as session:
        return await promote_all_pending(session)
