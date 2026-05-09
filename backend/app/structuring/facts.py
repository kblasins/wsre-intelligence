"""Route extracted facts from news articles to typed fact tables.

Each fact has a per-fact confidence (1-5):
  >= 4  → promoted directly to the typed table
  <= 3  → written to review_queue with source_table pointing to the typed table

Call promote_article_facts() after Sonnet extraction for every passing article.
Returns a FactRoutingResult with counts per destination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facts import (
    CapitalMarketsEvent,
    DemandSignal,
    InfrastructureEvent,
    MacroSignal,
    MarketCommentary,
    RegulatoryEvent,
    SupplyEvent,
    TenantSignal,
)
from app.models.review import ReviewQueue

log = structlog.get_logger(__name__)

PROMOTE_THRESHOLD = 4  # confidence >= this → promote; <= this-1 → review queue


@dataclass
class FactRoutingResult:
    promoted: dict[str, int] = field(default_factory=dict)
    queued: int = 0
    total: int = 0

    def add_promoted(self, table: str) -> None:
        self.promoted[table] = self.promoted.get(table, 0) + 1
        self.total += 1

    def add_queued(self) -> None:
        self.queued += 1
        self.total += 1


async def promote_article_facts(
    session: AsyncSession,
    article_id: int,
    facts: dict[str, Any],
    raw_uri: str | None,
    model_id: str | None,
    prompt_sha: str | None,
) -> FactRoutingResult:
    """Route all fact arrays from a Sonnet extraction to their tables.

    Also handles rent_movements via the existing promote_news_facts path
    (kept for backward compatibility).
    """
    result = FactRoutingResult()
    now = datetime.now(UTC)

    lineage = dict(
        article_id=article_id,
        raw_uri=raw_uri,
        extracted_at=now,
        prompt_sha=prompt_sha,
        model_id=model_id,
    )

    # ── supply_events ──────────────────────────────────────────────────────
    for fact in facts.get("supply_events", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(SupplyEvent(
                **lineage,
                confidence=conf,
                event_type=fact.get("event_type"),
                developer=fact.get("developer"),
                project_name=fact.get("project_name"),
                location_description=fact.get("location_description"),
                district_guess=fact.get("district_guess"),
                asset_class=fact.get("asset_class"),
                gfa_sqm=_float(fact.get("gfa_sqm")),
                land_area_sqm=_float(fact.get("land_area_sqm")),
                value_sar=_float(fact.get("value_sar")),
                expected_completion_date=fact.get("expected_completion_date"),
                anchor_tenants=fact.get("anchor_tenants") or [],
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("supply_events")
        else:
            _queue(session, "supply_events", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── regulatory_events ──────────────────────────────────────────────────
    for fact in facts.get("regulatory_events", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(RegulatoryEvent(
                **lineage,
                confidence=conf,
                event_type=fact.get("event_type"),
                authority=fact.get("authority"),
                scope=fact.get("scope"),
                effective_date=fact.get("effective_date"),
                summary=fact.get("summary"),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("regulatory_events")
        else:
            _queue(session, "regulatory_events", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── macro_signals ──────────────────────────────────────────────────────
    for fact in facts.get("macro_signals", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(MacroSignal(
                **lineage,
                confidence=conf,
                indicator=fact.get("indicator"),
                period=fact.get("period"),
                value=_float(fact.get("value")),
                direction=fact.get("direction"),
                magnitude=fact.get("magnitude"),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("macro_signals")
        else:
            _queue(session, "macro_signals", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── demand_signals ──────────────────────────────────────────────────────
    for fact in facts.get("demand_signals", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(DemandSignal(
                **lineage,
                confidence=conf,
                sector=fact.get("sector"),
                metric=fact.get("metric"),
                period=fact.get("period"),
                value=str(fact.get("value")) if fact.get("value") is not None else None,
                geography=fact.get("geography"),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("demand_signals")
        else:
            _queue(session, "demand_signals", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── capital_markets_events ──────────────────────────────────────────────
    for fact in facts.get("capital_markets_events", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(CapitalMarketsEvent(
                **lineage,
                confidence=conf,
                event_type=fact.get("event_type"),
                entity=fact.get("entity"),
                ticker_if_listed=fact.get("ticker_if_listed"),
                value_sar=_float(fact.get("value_sar")),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("capital_markets_events")
        else:
            _queue(session, "capital_markets_events", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── infrastructure_events ──────────────────────────────────────────────
    for fact in facts.get("infrastructure_events", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(InfrastructureEvent(
                **lineage,
                confidence=conf,
                project=fact.get("project"),
                infra_type=fact.get("infra_type") or fact.get("type"),
                phase=fact.get("phase"),
                location=fact.get("location"),
                completion_date=fact.get("completion_date"),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("infrastructure_events")
        else:
            _queue(session, "infrastructure_events", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── tenant_signals ──────────────────────────────────────────────────────
    for fact in facts.get("tenant_signals", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(TenantSignal(
                **lineage,
                confidence=conf,
                tenant_name=fact.get("tenant_name"),
                industry=fact.get("industry"),
                event_type=fact.get("event_type"),
                geography=fact.get("geography"),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("tenant_signals")
        else:
            _queue(session, "tenant_signals", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    # ── market_commentary ──────────────────────────────────────────────────
    for fact in facts.get("market_commentary", []):
        conf = _conf(fact)
        if conf >= PROMOTE_THRESHOLD:
            session.add(MarketCommentary(
                **lineage,
                confidence=conf,
                source_authority=fact.get("source_authority"),
                topic=fact.get("topic"),
                quote_under_15_words=fact.get("quote_under_15_words"),
                source_citation=fact.get("source_citation"),
            ))
            result.add_promoted("market_commentary")
        else:
            _queue(session, "market_commentary", article_id, raw_uri, model_id, prompt_sha, conf, fact)
            result.add_queued()

    return result


# ── helpers ────────────────────────────────────────────────────────────────


def _conf(fact: dict) -> int:
    """Parse confidence as 1-5 integer.

    Handles legacy float 0-1 scale from older prompt versions by scaling to 1-5.
    """
    raw = fact.get("confidence", 3)
    try:
        v = float(raw)
        if 0.0 < v <= 1.0 and v != int(v):
            # Old prompt returned 0-1 probability — scale to 1-5
            v = round(v * 5)
        return max(1, min(5, int(v)))
    except (TypeError, ValueError):
        return 3


def _float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _queue(
    session: AsyncSession,
    source_table: str,
    article_id: int,
    raw_uri: str | None,
    model_id: str | None,
    prompt_sha: str | None,
    confidence: int,
    fact: dict,
) -> None:
    uncertain = [k for k, v in fact.items() if v is None and k != "source_citation"]
    session.add(ReviewQueue(
        source_table=source_table,
        source_row_id=article_id,
        raw_uri=raw_uri,
        model_id=model_id,
        prompt_sha=prompt_sha,
        confidence=confidence,
        llm_output=fact,
        uncertain_fields=uncertain,
    ))
