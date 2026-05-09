"""Scheduler utility jobs — budget gate and materialized view refresh."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select, text

from app.core.database import AsyncSessionFactory
from app.models.llm import LLMCall

log = structlog.get_logger(__name__)

# When True, batch submissions are paused for the remainder of the UTC day.
# The flag is checked by the structuring pipeline before submitting Claude calls.
_batch_paused_until: datetime | None = None


def is_batch_paused() -> bool:
    """Return True if the daily budget gate has tripped and batches are paused."""
    global _batch_paused_until
    if _batch_paused_until is None:
        return False
    if datetime.now(UTC) >= _batch_paused_until:
        _batch_paused_until = None
        return False
    return True


async def check_llm_budget() -> None:
    """Sum today's LLM spend; pause batch jobs if the daily cap is hit.

    Called hourly. On breach:
      1. Sets _batch_paused_until to the start of the next UTC day
      2. Logs a warning that Sentry will capture as an alert
    """
    from app.core.config import settings

    global _batch_paused_until

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(
                LLMCall.called_at >= today_start
            )
        )
        daily_spend: float = float(result.scalar_one())

    log.info(
        "llm_budget_check",
        daily_spend_usd=round(daily_spend, 4),
        cap_usd=settings.claude_daily_budget_usd,
    )

    if daily_spend >= settings.claude_daily_budget_usd:
        tomorrow = today_start + timedelta(days=1)
        _batch_paused_until = tomorrow
        log.warning(
            "llm_daily_budget_breached",
            daily_spend_usd=round(daily_spend, 4),
            cap_usd=settings.claude_daily_budget_usd,
            paused_until=tomorrow.isoformat(),
        )


async def refresh_fact_resolved() -> None:
    """Refresh the fact_resolved materialized view (runs Sunday 05:00 UTC)."""
    async with AsyncSessionFactory() as session:
        await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY fact_resolved"))
        await session.commit()
    log.info("fact_resolved_refreshed")


async def refresh_district_velocity() -> None:
    """Refresh district_velocity materialized view (runs Sunday 03:00 UTC)."""
    async with AsyncSessionFactory() as session:
        await session.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY district_velocity")
        )
        await session.commit()
    log.info("district_velocity_refreshed")
