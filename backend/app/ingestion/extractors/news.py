"""Haiku 4.5 triage + Sonnet 4.6 extraction for news articles.

Two-pass LLM enrichment pipeline:
  Pass 1 (Haiku 4.5): Score each unscored article's relevance to the Saudi
      industrial/warehouse market. Fast, cheap — title-only input.
  Pass 2 (Sonnet 4.6): Extract structured_facts for articles scoring >= 0.5.
      Uses title + body (body may be null for list-scraped articles).

Entry point: run_news_extractor() — called by APScheduler every 4 hours.
Budget gate: checks is_batch_paused() before every pass.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import structlog
from anthropic import AsyncAnthropic
from sqlalchemy import select, update

from app.core.database import AsyncSessionFactory
from app.models.llm import LLMCall
from app.models.market import NewsArticle
from app.scheduler.jobs import is_batch_paused

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

TRIAGE_BATCH_SIZE = 50
EXTRACTION_BATCH_SIZE = 20
RELEVANCE_THRESHOLD = 0.35

# USD per 1M tokens — update this dict if Anthropic changes rates
PRICING: dict[str, dict[str, float]] = {
    HAIKU_MODEL: {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
    SONNET_MODEL: {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}

_TRIAGE_SYSTEM = """\
You are a relevance classifier for a Saudi Arabia industrial real estate intelligence system.

Score how useful this article title is for analysts tracking Saudi industrial real estate: \
warehouses, logistics, industrial land, REITs, commercial property, and their macro drivers.

SIGNAL CATEGORIES — any article with signal in one or more categories is relevant:

1. Real estate direct: transactions, rents, listings, property price indices, REIT dividends/NAV, \
project announcements, market reports (Knight Frank, CBRE, JLL), occupancy rates.

2. Regulatory: RE policy, zoning, RETT/WLT/property tax changes, foreign ownership rules, \
REGA licensing, rental platform rules (Ejar mandate), construction permits, MODON/SEZ \
announcements, planning decisions, vacant property fees.

3. Macro with RE linkage: SAMA interest rate decisions, CPI/construction-cost inflation, \
building permit counts, construction GDP contribution, PIF sector allocations.

4. Supply side: new developments by listed or large private developers, construction starts, \
industrial city expansions, mega-projects with land/GFA data, infrastructure (metro, highways, \
airports, ports) that affects logistics and industrial demand.

5. Demand side: e-commerce and delivery market volumes, manufacturing PMI, logistics network \
expansions, named-company tenant announcements, population/migration data tied to space demand.

6. Capital markets: Saudi REIT news (tickers 4331 4339 4340 4347 4338), developer IPOs/rights \
issues, real estate fund launches, institutional real estate investment announcements.

7. Infrastructure: metro, airport, port, highway projects; power/water for industrial zones; \
NEOM and special economic zone infrastructure.

SCORE CALIBRATION:
>=0.70: Strong direct signal — named deal, specific numbers, regulatory action, REIT disclosure.
  YES: "Jadwa REIT rental revenue up 21% Q1 2026"
  YES: "Crown Prince directs measures to balance Riyadh real estate sector"
  YES: "Building permits down 7% January 2026"
  YES: "REGA: rent payments via Ejar platform mandatory next month"

0.40-0.69: Useful context — market commentary, macro stat with RE linkage, supply/demand driver.
  YES: "Saudi delivery market surges 49% Q1 2026"
  YES: "Knight Frank: Riyadh metro impact on real estate"
  YES: "SAMA holds rate at 5.5%"
  YES: "Riyadh property price index down 1.6% Q1 2026"

0.20-0.39: Weak signal — tangentially related, minor context only.
  MAYBE: "Saudi Aramco announces $12B capex plan"
  MAYBE: "Petchem value chain localization deal"

<=0.15: Noise — not useful for Saudi RE analysis.
  NO: "Saudi minister meets foreign counterpart" (no RE policy)
  NO: "Bank quarterly earnings" (unless contains RE/REIT data)
  NO: "Gold or oil price movement" (commodity-only, no RE linkage stated)
  NO: "Sports, entertainment, general tech, pharma"

Respond ONLY with valid JSON — no prose, no markdown, no code fences.\
"""

_EXTRACTION_SYSTEM = """\
You are a structured data extractor for a Saudi Arabia industrial real estate intelligence database.

Extract only facts that are explicitly stated in the article. Do not invent data. \
Leave arrays empty when no relevant facts are present. Respond ONLY with valid JSON — \
no prose, no markdown, no code fences.\
"""

# f-string templates — prompt_sha is computed from the full template text
_TRIAGE_USER_TMPL = (
    'Title: {title}\n\nReturn exactly: {{"score": <0.0-1.0>, "reason": "<10 words>"}}'
)

_EXTRACTION_USER_TMPL = """\
Extract structured facts from this Saudi industrial real estate article.
RULES:
- Only extract facts EXPLICITLY stated in the text. Do not infer or fabricate.
- Every fact must include source_citation: a verbatim quote ≤15 words from the article.
- Leave arrays empty [] when no facts are present for that type.
- confidence is an INTEGER from 1 to 5 (not a decimal):
    5 = explicitly stated with specific numbers/dates
    4 = clearly stated but without full specifics
    3 = implied or paraphrased, plausible but uncertain
    2 = weak inference
    1 = speculation / title-only with no body support

Title: {title}
Body: {body}

Return JSON with these keys (all arrays, all optional):
{{
  "supply_events": [{{
    "event_type": "new_development|construction_start|completion|permit|land_allocation",
    "developer": null, "project_name": null, "location_description": null,
    "district_guess": null,
    "asset_class": "warehouse|industrial|office|mixed|residential|infrastructure",
    "gfa_sqm": null, "land_area_sqm": null, "value_sar": null,
    "expected_completion_date": null, "anchor_tenants": [],
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "regulatory_events": [{{
    "event_type": "new_law|amendment|consultation_open|enforcement_action|licensing_change",
    "authority": null, "scope": "nationwide|region|asset_class",
    "effective_date": null, "summary": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "macro_signals": [{{
    "indicator": "building_permits|construction_cost_index|property_price_index|SAMA_rate|inflation|GDP_construction|PIF_allocation|delivery_volume|other",
    "period": null, "value": null, "direction": "up|down|flat", "magnitude": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "demand_signals": [{{
    "sector": "e_commerce|logistics|manufacturing|retail|hospitality|office",
    "metric": null, "period": null, "value": null, "geography": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "capital_markets_events": [{{
    "event_type": "REIT_disclosure|fund_launch|IPO|rights_issue|acquisition|dividend",
    "entity": null, "ticker_if_listed": null, "value_sar": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "infrastructure_events": [{{
    "project": null,
    "infra_type": "transport|utility|industrial_zone|port|airport",
    "phase": null, "location": null, "completion_date": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "tenant_signals": [{{
    "tenant_name": null, "industry": null,
    "event_type": "expansion|new_lease|new_site|M_and_A|closure",
    "geography": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "market_commentary": [{{
    "source_authority": null, "topic": null,
    "quote_under_15_words": "<exact quote from article>",
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "rent_movements": [{{
    "district": null, "property_type": null,
    "direction": "up|down|flat", "change_pct": null, "period": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "overall_confidence": 4
}}\
"""


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences if present (model ignores the no-fence instruction)."""
    import re

    m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    return m.group(1).strip() if m else raw


def _parse_score(raw: str, article_id: int) -> float:
    """Parse a triage score from raw LLM output, stripping markdown fences if needed."""
    for attempt in (raw, _strip_fences(raw)):
        try:
            parsed = json.loads(attempt)
            score = float(parsed["score"])
            return max(0.0, min(1.0, score))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    log.warning("triage_parse_failed", article_id=article_id, raw=raw[:200])
    return 0.0


def _prompt_sha(system: str, user_tmpl: str) -> str:
    """First 12 hex chars of SHA-256 of the concatenated prompt templates."""
    return hashlib.sha256((system + user_tmpl).encode()).hexdigest()[:12]


def _compute_cost(usage: Any, model_id: str) -> float:
    """Compute USD cost from an Anthropic Usage object."""
    p = PRICING[model_id]
    return (
        usage.input_tokens * p["input"] / 1_000_000
        + usage.output_tokens * p["output"] / 1_000_000
        + getattr(usage, "cache_creation_input_tokens", 0) * p["cache_write"] / 1_000_000
        + getattr(usage, "cache_read_input_tokens", 0) * p["cache_read"] / 1_000_000
    )


async def run_news_extractor() -> None:
    """APScheduler entry point — triage then extraction, each in its own session."""
    if is_batch_paused():
        log.info("news_extractor_skipped", reason="daily_budget_reached")
        return

    async with AsyncSessionFactory() as session:
        triaged = await _run_triage(session)
    log.info("news_triage_done", triaged=triaged)

    if is_batch_paused():
        return

    async with AsyncSessionFactory() as session:
        extracted = await _run_extraction(session)
    log.info("news_extraction_done", extracted=extracted)


# ── Pass 1: Haiku triage ───────────────────────────────────────────────────────


async def _run_triage(session: AsyncSession) -> int:
    """Score articles with null relevance_score using Haiku 4.5."""
    result = await session.execute(
        select(NewsArticle)
        .where(NewsArticle.relevance_score.is_(None))
        .order_by(NewsArticle.created_at.asc())
        .limit(TRIAGE_BATCH_SIZE)
    )
    articles = list(result.scalars())
    if not articles:
        return 0

    from app.core.config import settings

    client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    count = 0

    for article in articles:
        title = article.title_en or article.title_ar or ""
        if not title:
            await session.execute(
                update(NewsArticle).where(NewsArticle.id == article.id).values(relevance_score=0.0)
            )
            continue

        try:
            score, call_row = await _triage_one(client, article.id, title)
        except Exception as exc:
            log.warning("triage_failed", article_id=article.id, error=str(exc))
            score = 0.0
            call_row = LLMCall(
                model_id=HAIKU_MODEL,
                prompt_sha=_prompt_sha(_TRIAGE_SYSTEM, _TRIAGE_USER_TMPL),
                task_type="news_triage",
                input_tokens=0,
                output_tokens=0,
                cache_write_tokens=0,
                cache_read_tokens=0,
                cost_usd=0.0,
                article_id=article.id,
                success=False,
                error_message=str(exc)[:500],
            )

        session.add(call_row)
        await session.execute(
            update(NewsArticle).where(NewsArticle.id == article.id).values(relevance_score=score)
        )
        count += 1

    await session.commit()
    return count


async def _triage_one(client: AsyncAnthropic, article_id: int, title: str) -> tuple[float, LLMCall]:
    prompt_sha = _prompt_sha(_TRIAGE_SYSTEM, _TRIAGE_USER_TMPL)
    user_msg = _TRIAGE_USER_TMPL.format(title=title[:500])

    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=64,
        system=[{"type": "text", "text": _TRIAGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    score = _parse_score(raw, article_id)

    call_row = LLMCall(
        model_id=HAIKU_MODEL,
        prompt_sha=prompt_sha,
        task_type="news_triage",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
        cost_usd=_compute_cost(response.usage, HAIKU_MODEL),
        article_id=article_id,
        success=True,
    )
    return score, call_row


# ── Pass 2: Sonnet extraction ─────────────────────────────────────────────────


async def _run_extraction(session: AsyncSession) -> int:
    """Extract structured_facts for relevant articles using Sonnet 4.6."""
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    from sqlalchemy import text as sa_text

    result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.relevance_score >= RELEVANCE_THRESHOLD,
            sa_text("structured_facts = '{}'::jsonb"),
        )
        .order_by(NewsArticle.created_at.asc())
        .limit(EXTRACTION_BATCH_SIZE)
    )
    articles = list(result.scalars())
    if not articles:
        return 0

    from app.core.config import settings

    client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    count = 0

    for article in articles:
        title = article.title_en or article.title_ar or ""
        if not title:
            continue

        body = article.body_en or article.body_ar or ""

        try:
            facts, call_row = await _extract_one(client, article.id, title, body)
        except Exception as exc:
            log.warning("extraction_failed", article_id=article.id, error=str(exc))
            call_row = LLMCall(
                model_id=SONNET_MODEL,
                prompt_sha=_prompt_sha(_EXTRACTION_SYSTEM, _EXTRACTION_USER_TMPL),
                task_type="news_extraction",
                input_tokens=0,
                output_tokens=0,
                cache_write_tokens=0,
                cache_read_tokens=0,
                cost_usd=0.0,
                article_id=article.id,
                success=False,
                error_message=str(exc)[:500],
            )
            session.add(call_row)
            # Use a sentinel so this article isn't retried in the same batch
            await session.execute(
                update(NewsArticle)
                .where(NewsArticle.id == article.id)
                .values(structured_facts={"_extraction_failed": True})
            )
            continue

        overall_confidence = facts.pop("overall_confidence", None)
        session.add(call_row)
        await session.execute(
            update(NewsArticle)
            .where(NewsArticle.id == article.id)
            .values(
                structured_facts=facts,
                model_id=SONNET_MODEL,
                prompt_sha=call_row.prompt_sha,
                confidence=overall_confidence,
            )
        )

        # Route each fact type to its table (promote >= 4, queue <= 3)
        try:
            from app.structuring.facts import promote_article_facts

            routing = await promote_article_facts(
                session,
                article.id,
                facts,
                article.raw_uri,
                SONNET_MODEL,
                call_row.prompt_sha,
            )
            if routing.total:
                log.info(
                    "facts_routed",
                    article_id=article.id,
                    promoted=routing.promoted,
                    queued=routing.queued,
                )
        except Exception as exc:
            log.warning("facts_routing_failed", article_id=article.id, error=str(exc))

        # Also run legacy rent_movements promoter for RentIndex backward compat
        if facts.get("rent_movements"):
            try:
                from app.structuring.news import promote_news_facts

                await promote_news_facts(
                    session,
                    article.id,
                    facts,
                    article.raw_uri,
                    SONNET_MODEL,
                    call_row.prompt_sha,
                )
            except Exception as exc:
                log.warning("news_promote_failed", article_id=article.id, error=str(exc))

        count += 1

    await session.commit()
    return count


async def _extract_one(
    client: AsyncAnthropic, article_id: int, title: str, body: str
) -> tuple[dict, LLMCall]:
    prompt_sha = _prompt_sha(_EXTRACTION_SYSTEM, _EXTRACTION_USER_TMPL)
    body_text = body[:3000] if body else "(article body not yet fetched)"
    user_msg = _EXTRACTION_USER_TMPL.format(title=title[:500], body=body_text)

    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=3000,
        system=[
            {"type": "text", "text": _EXTRACTION_SYSTEM, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    facts = None
    for attempt in (raw, _strip_fences(raw)):
        try:
            parsed = json.loads(attempt)
            if isinstance(parsed, dict):
                facts = parsed
                break
        except (json.JSONDecodeError, ValueError):
            pass
    if facts is None:
        log.warning("extraction_parse_failed", article_id=article_id, raw=raw[:200])
        facts = {"_raw_response": raw[:500], "confidence": 1}

    call_row = LLMCall(
        model_id=SONNET_MODEL,
        prompt_sha=prompt_sha,
        task_type="news_extraction",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
        cost_usd=_compute_cost(response.usage, SONNET_MODEL),
        article_id=article_id,
        success=True,
    )
    return facts, call_row
