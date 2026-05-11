"""Warsaw-tuned Haiku triage + Sonnet extraction for Polish news articles.

Identical pipeline to extractors/news.py but with:
  - Warsaw RE triage system prompt (Polish market categories)
  - Warsaw extraction prompt (PLN, Polish authorities, Polish geography)
  - Only processes articles from Polish sources (eurobuild_cee, money_pl_nieruch)

Entry points:
  run_warsaw_triage(session)      — score unscored articles from Polish sources
  run_warsaw_extraction(session)  — extract facts from triage-passed Polish articles
  run_warsaw_news_pipeline()      — triage + extraction in sequence

The 8 typed fact tables are unchanged — Polish facts land in the same tables
as Saudi facts, distinguishable by article.source.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from anthropic import AsyncAnthropic
from sqlalchemy import select, update

from app.core.database import AsyncSessionFactory
from app.models.llm import LLMCall
from app.models.market import NewsArticle

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

TRIAGE_BATCH_SIZE = 50
EXTRACTION_BATCH_SIZE = 20
RELEVANCE_THRESHOLD = 0.6   # Higher bar for Polish brief (spec: ≥0.6)

# Polish news sources this extractor processes
POLISH_SOURCES = ("eurobuild_cee", "inwestycje_pl")

# USD per 1M tokens
_PRICING: dict[str, dict[str, float]] = {
    HAIKU_MODEL: {"input": 0.80, "output": 4.00, "cache_write": 1.00, "cache_read": 0.08},
    SONNET_MODEL: {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
}


# ── Warsaw triage system prompt ───────────────────────────────────────────────

_WARSAW_TRIAGE_SYSTEM = """\
You are a relevance classifier for a Warsaw, Poland real estate intelligence system.

Score how useful this article is for analysts tracking Warsaw commercial and residential \
real estate: offices, primary residential (new-build), investment transactions, \
capital markets, and their macro drivers.

SIGNAL CATEGORIES — any article with signal in one or more categories is relevant:

1. Real estate direct: residential developer launches, flat prices (PLN/m²), \
transaction volumes, office leasing (absorption, vacancy, headline rents in EUR/m²/month), \
retail/logistics/mixed-use in Warsaw, market reports (JLL, CBRE, Colliers, Cushman, \
Savills, Knight Frank Poland).

2. Regulatory: Polish planning law (ustawa deweloperska, MPZP, warunki zabudowy), \
zoning decisions, heritage/conservation rulings, building permit statistics, \
environmental clearances, Warsaw City Council RE decisions, Ministry of Development \
(MRiT) policy changes.

3. Macro with RE linkage: NBP interest rate decisions, WIRON/WIBOR movements, \
PKB (GDP) construction component, CPI / construction cost inflation, mortgage market \
statistics (BIK, ZBP data), EUR/PLN for investment pricing.

4. Supply side: new office/residential projects announced or delivered, \
developer pipeline updates (Develia, Echo Investment, Ghelamco, HB Reavis, \
Skanska, Golub GetHouse, Cornerstone, Victoria Dom, Robyg, Dom Development, Murapol etc.), \
construction starts and completions with GFA/PUM data.

5. Demand side: corporate relocations and office leases (named tenant + sqm + location), \
co-working expansion, Warsaw absorption data, residential pre-sale rates.

6. Capital markets: institutional acquisition/sale in Warsaw (office towers, \
logistics parks, retail), fund commitments (Blackstone, Patrizia, Nuveen, EPP, \
Griffin Real Estate, etc.), Polish RE investment funds (FIZ AN), REIT-equivalent vehicles.

7. Infrastructure: Metro C line progress, tram network extensions in Warsaw, \
S-Bahn (SKM/KM) upgrades, airport development (CPK / Okęcie), road projects \
affecting Warsaw logistics catchment.

SCORE CALIBRATION:
>=0.70: Strong direct signal — named deal, specific numbers, regulatory decision, \
named developer with price/area data, named corporate lease.
  YES: "Dom Development sprzedał 620 mieszkań w Q1 2026 w Warszawie"
  YES: "Ghelamco delivers Generation Park Y — 52,000 sqm, Warsaw"
  YES: "NBP keeps reference rate at 5.25% — mortgage implications"
  YES: "CBRE: Warsaw office vacancy falls to 10.3%, rents up to EUR 27/sqm/month"
  YES: "Blackstone acquires Warsaw logistics portfolio for €180m"

0.40-0.69: Useful context — market commentary, macro stat with RE linkage, \
supply/demand driver without specific numbers.
  YES: "Warsaw prime office yields compress amid investor demand"
  YES: "Polish construction sector PMI stabilises at 52.1"
  YES: "New housing supply in Poland down 8% YoY — GUS data"
  YES: "Wola district transformation: office-to-residential conversion trend"

0.20-0.39: Weak signal — tangentially related, minor context only.
  MAYBE: "Polish retail sales growth supports consumption outlook"
  MAYBE: "General EU interest rate commentary without Poland specifics"

<=0.15: Noise — not useful for Warsaw RE analysis.
  NO: "Krakow or Wroclaw office deal with no Warsaw angle"
  NO: "General Polish politics, sports, entertainment, pharma"
  NO: "CEE-wide macro with no Poland-specific content"
  NO: "Retail consumer news without commercial RE angle"

Respond ONLY with valid JSON — no prose, no markdown, no code fences.\
"""

_WARSAW_TRIAGE_USER_TMPL = (
    'Title: {title}\n\nReturn exactly: {{"score": <0.0-1.0>, "reason": "<10 words>"}}'
)


# ── Warsaw extraction system prompt ──────────────────────────────────────────

_WARSAW_EXTRACTION_SYSTEM = """\
You are a structured data extractor for a Warsaw, Poland real estate intelligence database.

LANGUAGE: Articles may be in English or Polish. Extract data from either language.
GEOGRAPHY: Focus on Warsaw and Poland. Preserve Polish place names as-is \
(Wola, Mokotów, Śródmieście, Praga-Północ, Żoliborz, Ursynów, Wilanów, etc.).
CURRENCIES: Preserve original currency. Use PLN for złoty amounts, EUR for euro amounts. \
Do not convert. Residential prices are typically PLN/m². Office rents are EUR/m²/month.
AUTHORITIES: Polish authorities include NBP, GUS, MRiT, UOKiK, BIK, ZBP, \
Warsaw City Council (Rada m.st. Warszawy), UKNF, KNF.
DEVELOPERS: Preserve full Polish developer names (Dom Development, Develia, Murapol, \
Victoria Dom, Robyg, Atal, Echo Investment, HB Reavis, Ghelamco, Skanska, etc.).
TENANTS: Named corporate tenants taking office space — capture company name, sqm, location.

Extract only facts that are explicitly stated in the article. Do not invent data. \
Leave arrays empty when no relevant facts are present. \
Respond ONLY with valid JSON — no prose, no markdown, no code fences.\
"""

_WARSAW_EXTRACTION_USER_TMPL = """\
Extract structured facts from this Warsaw / Poland real estate article.
RULES:
- Only extract facts EXPLICITLY stated in the text. Do not infer or fabricate.
- Every fact must include source_citation: a verbatim quote ≤15 words from the article.
- Leave arrays empty [] when no facts are present for that type.
- confidence is an INTEGER from 1 to 5:
    5 = explicitly stated with specific numbers/dates/names
    4 = clearly stated but without full specifics
    3 = implied or paraphrased, plausible but uncertain
    2 = weak inference
    1 = speculation / title-only with no body support
- For monetary values: use PLN for residential/Polish domestic pricing, EUR for \
  commercial investment/leasing (as is common in Polish RE reporting).

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
    "indicator": "NBP_rate|WIRON|EUR_PLN|CPI|construction_cost|GDP_construction|building_permits|mortgage_volume|property_price_index|other",
    "period": null, "value": null, "direction": "up|down|flat", "magnitude": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "demand_signals": [{{
    "sector": "office|residential|retail|logistics|manufacturing|hospitality",
    "metric": null, "period": null, "value": null, "geography": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "capital_markets_events": [{{
    "event_type": "acquisition|disposal|fund_launch|fund_commitment|refinancing|JV",
    "entity": null, "ticker_if_listed": null, "value_sar": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "infrastructure_events": [{{
    "project": null,
    "infra_type": "transport|metro|tram|road|utility|airport",
    "phase": null, "location": null, "completion_date": null,
    "source_citation": "<verbatim quote ≤15 words>", "confidence": 4
  }}],
  "tenant_signals": [{{
    "tenant_name": null, "industry": null,
    "event_type": "expansion|new_lease|renewal|new_site|M_and_A|closure",
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


# ── Pipeline entry points ──────────────────────────────────────────────────────


async def run_warsaw_triage(session: AsyncSession) -> int:
    """Score unscored articles from Polish sources using Warsaw-tuned Haiku prompt."""
    sources_sql = ", ".join(f"'{s}'" for s in POLISH_SOURCES)

    result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.relevance_score.is_(None),
            NewsArticle.source.in_(POLISH_SOURCES),
        )
        .order_by(NewsArticle.created_at.asc())
        .limit(TRIAGE_BATCH_SIZE)
    )
    articles = list(result.scalars())
    if not articles:
        return 0

    from app.core.config import settings as app_settings
    client = AsyncAnthropic(api_key=app_settings.anthropic_api_key or None)
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
            log.warning("warsaw_triage_failed", article_id=article.id, error=str(exc))
            score = 0.0
            call_row = LLMCall(
                model_id=HAIKU_MODEL,
                prompt_sha=_prompt_sha(_WARSAW_TRIAGE_SYSTEM, _WARSAW_TRIAGE_USER_TMPL),
                task_type="news_triage_warsaw",
                input_tokens=0, output_tokens=0,
                cache_write_tokens=0, cache_read_tokens=0,
                cost_usd=0.0, article_id=article.id,
                success=False, error_message=str(exc)[:500],
            )

        session.add(call_row)
        await session.execute(
            update(NewsArticle).where(NewsArticle.id == article.id).values(relevance_score=score)
        )
        count += 1

    await session.commit()
    return count


async def run_warsaw_extraction(session: AsyncSession) -> int:
    """Extract structured facts for triage-passed Polish articles using Sonnet."""
    from sqlalchemy import text as sa_text

    result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.relevance_score >= RELEVANCE_THRESHOLD,
            NewsArticle.source.in_(POLISH_SOURCES),
            sa_text("structured_facts = '{}'::jsonb"),
        )
        .order_by(NewsArticle.relevance_score.desc())
        .limit(EXTRACTION_BATCH_SIZE)
    )
    articles = list(result.scalars())
    if not articles:
        return 0

    from app.core.config import settings as app_settings
    client = AsyncAnthropic(api_key=app_settings.anthropic_api_key or None)
    count = 0

    for article in articles:
        title = article.title_en or article.title_ar or ""
        if not title:
            continue
        body = article.body_en or article.body_ar or ""

        try:
            facts, call_row = await _extract_one(client, article.id, title, body)
        except Exception as exc:
            log.warning("warsaw_extraction_failed", article_id=article.id, error=str(exc))
            call_row = LLMCall(
                model_id=SONNET_MODEL,
                prompt_sha=_prompt_sha(_WARSAW_EXTRACTION_SYSTEM, _WARSAW_EXTRACTION_USER_TMPL),
                task_type="news_extraction_warsaw",
                input_tokens=0, output_tokens=0,
                cache_write_tokens=0, cache_read_tokens=0,
                cost_usd=0.0, article_id=article.id,
                success=False, error_message=str(exc)[:500],
            )
            session.add(call_row)
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

        # Route facts to typed tables
        try:
            from app.structuring.facts import promote_article_facts
            routing = await promote_article_facts(
                session, article.id, facts,
                article.raw_uri, SONNET_MODEL, call_row.prompt_sha,
            )
            if routing.total:
                log.info(
                    "warsaw_facts_routed",
                    article_id=article.id,
                    promoted=routing.promoted,
                    queued=routing.queued,
                )
        except Exception as exc:
            log.warning("warsaw_facts_routing_failed", article_id=article.id, error=str(exc))

        count += 1

    await session.commit()
    return count


async def run_warsaw_news_pipeline() -> None:
    """Run full triage + extraction for Polish sources. Called from APScheduler."""
    async with AsyncSessionFactory() as session:
        triaged = await run_warsaw_triage(session)
    log.info("warsaw_triage_done", triaged=triaged)

    async with AsyncSessionFactory() as session:
        extracted = await run_warsaw_extraction(session)
    log.info("warsaw_extraction_done", extracted=extracted)


# ── LLM call helpers ──────────────────────────────────────────────────────────


def _prompt_sha(system: str, user_tmpl: str) -> str:
    return hashlib.sha256((system + user_tmpl).encode()).hexdigest()[:12]


def _compute_cost(usage: Any, model_id: str) -> float:
    p = _PRICING[model_id]
    return (
        usage.input_tokens * p["input"] / 1_000_000
        + usage.output_tokens * p["output"] / 1_000_000
        + getattr(usage, "cache_creation_input_tokens", 0) * p["cache_write"] / 1_000_000
        + getattr(usage, "cache_read_input_tokens", 0) * p["cache_read"] / 1_000_000
    )


def _strip_fences(raw: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    return m.group(1).strip() if m else raw


def _parse_score(raw: str, article_id: int) -> float:
    for attempt in (raw, _strip_fences(raw)):
        try:
            parsed = json.loads(attempt)
            score = float(parsed["score"])
            return max(0.0, min(1.0, score))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    log.warning("warsaw_triage_parse_failed", article_id=article_id, raw=raw[:200])
    return 0.0


async def _triage_one(
    client: AsyncAnthropic, article_id: int, title: str
) -> tuple[float, LLMCall]:
    sha = _prompt_sha(_WARSAW_TRIAGE_SYSTEM, _WARSAW_TRIAGE_USER_TMPL)
    user_msg = _WARSAW_TRIAGE_USER_TMPL.format(title=title[:500])

    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=64,
        system=[{"type": "text", "text": _WARSAW_TRIAGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    score = _parse_score(raw, article_id)

    call_row = LLMCall(
        model_id=HAIKU_MODEL,
        prompt_sha=sha,
        task_type="news_triage_warsaw",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
        cost_usd=_compute_cost(response.usage, HAIKU_MODEL),
        article_id=article_id,
        success=True,
    )
    return score, call_row


async def _extract_one(
    client: AsyncAnthropic, article_id: int, title: str, body: str
) -> tuple[dict, LLMCall]:
    sha = _prompt_sha(_WARSAW_EXTRACTION_SYSTEM, _WARSAW_EXTRACTION_USER_TMPL)
    body_text = body[:4000] if body else "(article body not yet fetched)"
    user_msg = _WARSAW_EXTRACTION_USER_TMPL.format(
        title=title[:500], body=body_text
    )

    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=3000,
        system=[{"type": "text", "text": _WARSAW_EXTRACTION_SYSTEM, "cache_control": {"type": "ephemeral"}}],
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
        log.warning("warsaw_extraction_parse_failed", article_id=article_id, raw=raw[:200])
        facts = {"_raw_response": raw[:500], "confidence": 1}

    call_row = LLMCall(
        model_id=SONNET_MODEL,
        prompt_sha=sha,
        task_type="news_extraction_warsaw",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
        cost_usd=_compute_cost(response.usage, SONNET_MODEL),
        article_id=article_id,
        success=True,
    )
    return facts, call_row
