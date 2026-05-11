"""Warsaw weekly brief orchestrator — Opus 4.6 synthesis (Polish RE edition).

Entry point: run_weekly_brief_warsaw()
Parallel to app/briefing/orchestrator.py but for Warsaw commercial and residential RE.

Pipeline:
  1. Build Warsaw context via build_warsaw_context() (Jawność + typed facts with geo-filter
     + macro + news + regulatory)
  2. Guardrail 1: Warsaw geographic filter applied inside warsaw_context._facts_section()
  3. Call Opus 4.6 with Polish-tuned system prompt (Guardrails 2 + 3)
  4. Parse JSON, validate schema
  5. Store WeeklyBrief row (brief_json includes _market="warsaw")
  6. Return brief for review — PDF render is a separate step

Guardrails baked into system prompt:
  G1 — Warsaw geographic filter (applied in context assembler, reported in _facts_stats)
  G2 — Attribution accuracy enforcement (entity role disambiguation, single-source tracing)
  G3 — Banned vocabulary list (institutional research voice enforcement)
"""

from __future__ import annotations

import decimal
import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from sqlalchemy import select, text

from app.briefing.warsaw_context import build_warsaw_context
from app.core.database import AsyncSessionFactory
from app.core.storage import upload_raw
from app.models.brief import WeeklyBrief
from app.models.llm import LLMCall

log = structlog.get_logger(__name__)

OPUS_MODEL = "claude-opus-4-6"

# USD per 1M tokens (Opus 4.6 pricing)
_OPUS_PRICING = {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50}

# ── System prompt: Guardrails 2 + 3 + Warsaw editorial rules ─────────────────

_SYSTEM_PROMPT = """\
You are a senior research analyst at WSRE Intelligence, a Warsaw real estate advisory firm \
serving institutional investors. Your weekly brief is the authoritative view of the Warsaw \
commercial and residential real estate market, distributed to fund managers and developers \
every Monday before the trading week opens.

EDITORIAL VOICE: Knight Frank / CBRE / JLL quarterly research note tone. Precise, institutional, \
evidence-based. Specific named entities, values with units, dates wherever the data supports it. \
Never overstate; acknowledge uncertainty and data gaps explicitly — institutional readers trust \
the brief because it is honest about limits.

ATTRIBUTION (mandatory — Guardrail 2):
For every named transaction, lease, or deal in the brief, verify that entity attribution \
matches the source citation exactly. If the source article mentions multiple companies, \
distinguish their roles clearly (buyer, seller, target, advisor). When in doubt, attribute \
conservatively — use the source's exact phrasing rather than inferring relationships. \
Do not combine separate transactions into one entry. Each fact in the brief must trace to \
exactly one source citation.

CURRENCY AND UNITS:
- PLN for residential amounts (e.g. PLN 12,500/m²) and Polish domestic metrics
- EUR for commercial investment and leasing figures (e.g. EUR 24/m²/month)
- Do not convert between currencies — report as sourced
- Dates in DD MMM YYYY format (e.g. 07 May 2026)
- Areas in sqm; volumes in M EUR or M PLN with the M notation

GEOGRAPHIC SCOPE:
Exclude facts geographically scoped exclusively to non-Warsaw Polish cities (Kraków, Wrocław, \
Łódź, Poznań, Gdańsk, Gdynia, Katowice, Lublin) unless they also provide explicit Warsaw or \
Poland-wide context relevant to Warsaw investors.

BANNED WORDS (Guardrail 3 — never use):
English: seamlessly, leverage, harness, unlock, empower, robust, cutting-edge, elevate, \
streamline, comprehensive, dive in, transform, navigate (as verb), journey, unleash, \
foster (in "foster innovation" sense), pivotal, paradigm, ecosystem, game-changing, \
best-in-class, world-class, state-of-the-art
Polish marketing language: wykorzystać potencjał, transformacja cyfrowa, wzmocnić pozycję, \
rewolucja rynkowa, ekosystem startupów, dynamiczny rozwój (when used as filler)

OUTPUT FORMAT: You must output ONLY a valid JSON object. No prose outside the JSON. \
No markdown code fences. No commentary before or after the JSON. \
Start your response with { and end with }.

JSON SCHEMA (all keys required; use null for unavailable data):
{
  "headline": "≤12-word news-wire style headline for the week",
  "subhead": "≤25-word expansion giving key figures or context",
  "editors_note": "3-5 sentences focused exclusively on market thesis: the week's dominant \
theme(s) with cited evidence, any material forecast revisions this evidence supports, and a \
brief forward-looking view for investors. Maximum one sentence acknowledging a single key \
uncertainty — not an enumerated list of unpopulated tables. Data methodology and coverage \
gaps belong in sources_footer, not here.",
  "sections": [
    {
      "id": "capital_markets|supply_pipeline|office_market|residential|macro|regulatory",
      "title": "4-6 word section title",
      "body": "3-6 sentences of analysis. Integrate at least 3 cited facts from the \
provided data. Be specific — named entities, values with units, dates. Each material \
claim must reference a fact from the data above.",
      "key_facts": [
        {
          "description": "one-sentence fact statement with entity + value + date where available",
          "entity": "company or developer name, or null",
          "value": "numeric value with unit, or null",
          "currency": "PLN|EUR|null",
          "date_or_period": "date or period string, or null",
          "citation": "verbatim ≤15 words from the source_citation field"
        }
      ]
    }
  ],
  "macro_highlights": [
    {
      "indicator": "indicator name",
      "value": "value with unit",
      "period": "period string",
      "direction": "up|down|flat",
      "implication": "≤15-word implication for Warsaw RE investment"
    }
  ],
  "watch_list": [
    {
      "item": "specific thing to monitor",
      "trigger": "exact condition that would change the market view",
      "timeline": "by DD MMM YYYY or next week"
    }
  ],
  "sources_footer": "Compiled from N facts across M source(s) for the week ending DD MMM YYYY. \
[Data source disclosures — residential feed, broker report sourcing, macro feed cadence]. \
This brief is for the named recipient only. Not investment advice."
}

Constraints:
- sections: 3-5 entries; prioritise capital_markets and supply_pipeline where data is richest
- key_facts per section: 2-6 entries; only facts traceable to the provided data
- macro_highlights: include all significant indicators present in the data
- watch_list: exactly 3 items with specific, measurable triggers
- editors_note: 3-5 sentences of market thesis only; max one uncertainty sentence; no data gap enumeration
- sources_footer: methodology disclosure in neutral institutional tone; not an apology; \
mention fact count, sources, residential data origin, broker report sourcing caveat, macro feed cadence\
"""


_USER_PROMPT_TMPL = """\
Generate the WSRE Intelligence Warsaw weekly market brief for the week ending {week_ending_long}.

## PRIMARY RESIDENTIAL MARKET (JAWNOŚĆ / DANE.GOV.PL)
{jawnosc_signals}

## POLISH MACRO INDICATORS
{macro}

## NEWS (eurobuild_cee, inwestycje_pl — last 30 days)
{news}

## REGULATORY EVENTS (Warsaw + Poland)
{regulatory}

## EXTRACTED FACTS — WARSAW GEO-FILTERED
{facts}

## DATA QUALITY NOTES
{data_notes}

---

Synthesise the above into a Warsaw market intelligence brief. \
The EXTRACTED FACTS section is the primary signal source — weight it most heavily. \
The news section provides article-level context for the brief narrative. \
Jawność data provides residential price signals; if the table is empty, acknowledge the gap \
explicitly in the editors_note. \
Do not fabricate or infer data not present in the sections above. \
Start your response with {{ and end with }}.\
"""


def _prompt_sha() -> str:
    return hashlib.sha256((_SYSTEM_PROMPT + _USER_PROMPT_TMPL).encode()).hexdigest()[:12]


def _compute_cost(usage: Any) -> float:
    p = _OPUS_PRICING
    return (
        usage.input_tokens * p["input"] / 1_000_000
        + usage.output_tokens * p["output"] / 1_000_000
        + getattr(usage, "cache_creation_input_tokens", 0) * p["cache_write"] / 1_000_000
        + getattr(usage, "cache_read_input_tokens", 0) * p["cache_read"] / 1_000_000
    )


def _parse_brief_json(raw: str) -> dict:
    """Parse Opus JSON-only response. Strips fences if accidentally present."""
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        log.warning("warsaw_brief_json_parse_failed", raw_preview=t[:300])
        return {"editors_note": t[:800], "_parse_error": True}


def _format_date_long(d: date) -> str:
    return d.strftime("%-d %B %Y")


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    return obj


async def run_weekly_brief_warsaw(
    week_ending: date | None = None,
    force: bool = False,
    save: bool = True,
) -> tuple[WeeklyBrief | None, dict]:
    """Generate the Warsaw weekly brief. Returns (WeeklyBrief row or None, report_dict).

    Args:
        week_ending: Date to generate for; defaults to today.
        force: If True, delete any existing Warsaw brief for this date and regenerate.
        save:  If False, generate but do not persist to DB (dry-run for review).

    report_dict contains:
        - facts_stats: per-table Warsaw geo-filter counts
        - cost_usd: Opus call cost
        - input_tokens / output_tokens
        - headline / subhead / editors_note (for quick review)
        - sections_count
    """
    if week_ending is None:
        week_ending = date.today()

    log.info("warsaw_brief_start", week_ending=str(week_ending), force=force)

    async with AsyncSessionFactory() as session:
        if force and save:
            await session.execute(
                text(
                    "DELETE FROM weekly_briefs "
                    "WHERE week_ending = :d AND brief_json->>'_market' = 'warsaw'"
                ),
                {"d": week_ending},
            )
            await session.commit()

        if save:
            existing = await session.execute(
                select(WeeklyBrief).where(
                    WeeklyBrief.week_ending == week_ending,
                )
            )
            row = existing.scalar_one_or_none()
            if row and row.brief_json.get("_market") == "warsaw":
                log.info("warsaw_brief_already_exists", week_ending=str(week_ending))
                return row, {"cached": True}

        # ── Build context ─────────────────────────────────────────────────────
        context = await build_warsaw_context(session, week_ending)
        facts_stats = context.get("_facts_stats", {})
        total_warsaw_facts = sum(v.get("warsaw", 0) for v in facts_stats.values())
        log.info(
            "warsaw_brief_context_built",
            week_ending=str(week_ending),
            facts_total=sum(v.get("total", 0) for v in facts_stats.values()),
            facts_warsaw=total_warsaw_facts,
        )

        # ── Call Opus 4.6 ─────────────────────────────────────────────────────
        from app.core.config import settings

        client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)

        user_msg = _USER_PROMPT_TMPL.format(
            week_ending_long=_format_date_long(week_ending),
            jawnosc_signals=context["jawnosc_signals"],
            macro=context["macro"],
            news=context["news"],
            regulatory=context["regulatory"],
            facts=context["facts"],
            data_notes=context["data_notes"],
        )

        response = await client.messages.create(
            model=OPUS_MODEL,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )

        raw_response = response.content[0].text
        opus_json = _parse_brief_json(raw_response)
        cost = _compute_cost(response.usage)

        log.info(
            "warsaw_brief_generated",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_write=getattr(response.usage, "cache_creation_input_tokens", 0),
            cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
            cost_usd=round(cost, 4),
        )

        # ── Merge Opus JSON with authoritative context data ───────────────────
        brief_json: dict[str, Any] = _json_safe({
            **opus_json,
            "_market": "warsaw",
            "_kpi_strip": context["_kpi_strip"],
            "_price_by_district": context["_price_by_district"],
            "_macro_table": context["_macro_table"],
            "_regulatory_events": context["_regulatory_events"],
            "_facts_stats": facts_stats,
            "_week_ending": week_ending.isoformat(),
            "_week_ending_long": _format_date_long(week_ending),
            "_model_id": OPUS_MODEL,
            "_cost_usd": round(cost, 6),
            "_input_tokens": response.usage.input_tokens,
            "_output_tokens": response.usage.output_tokens,
            "_warsaw_facts_total": total_warsaw_facts,
        })

        report = {
            "facts_stats": facts_stats,
            "facts_warsaw_total": total_warsaw_facts,
            "cost_usd": round(cost, 4),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "headline": opus_json.get("headline", "(parse error)"),
            "subhead": opus_json.get("subhead", ""),
            "editors_note": opus_json.get("editors_note", ""),
            "sections_count": len(opus_json.get("sections", [])),
            "parse_error": opus_json.get("_parse_error", False),
        }

        if not save:
            log.info("warsaw_brief_dry_run_complete", cost_usd=round(cost, 4))
            return None, {**report, "brief_json": brief_json}

        # ── Persist ───────────────────────────────────────────────────────────
        raw_bytes = raw_response.encode()
        uri, _ = await upload_raw(
            raw_bytes, "brief", "md",
            content_type="text/plain",
            ts=datetime.now(UTC),
        )

        brief_row = WeeklyBrief(
            week_ending=week_ending,
            brief_text=raw_response,
            brief_json=brief_json,
            model_id=OPUS_MODEL,
            prompt_sha=_prompt_sha(),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            pdf_uri=None,
        )
        session.add(brief_row)

        session.add(
            LLMCall(
                model_id=OPUS_MODEL,
                prompt_sha=_prompt_sha(),
                task_type="weekly_brief_warsaw",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
                cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
                cost_usd=cost,
                success=True,
            )
        )

        await session.commit()
        log.info(
            "warsaw_brief_stored",
            week_ending=str(week_ending),
            uri=uri,
            cost_usd=round(cost, 4),
        )

        return brief_row, report


if __name__ == "__main__":
    import asyncio
    import sys

    from app.core.logging import configure_logging

    configure_logging()

    args = sys.argv[1:]
    force = "--force" in args
    dry_run = "--dry-run" in args
    date_args = [a for a in args if not a.startswith("--")]
    target = date.fromisoformat(date_args[0]) if date_args else date.today()

    brief_row, report = asyncio.run(
        run_weekly_brief_warsaw(target, force=force, save=not dry_run)
    )

    print(f"\n{'=' * 65}")
    print(f"WARSAW BRIEF — WEEK ENDING {target}")
    print(f"{'=' * 65}")
    print(f"  Parse error:    {report.get('parse_error', False)}")
    print(f"  Sections:       {report.get('sections_count', 0)}")
    print(f"  Warsaw facts:   {report.get('facts_warsaw_total', 0)} (surviving geo-filter)")
    print(f"  Tokens:         {report.get('input_tokens', 0)} in / {report.get('output_tokens', 0)} out")
    print(f"  Cost:           ${report.get('cost_usd', 0):.4f}")
    print(f"\nHEADLINE: {report.get('headline', '')}")
    print(f"SUBHEAD:  {report.get('subhead', '')}")
    print(f"\nEDITOR'S NOTE:\n{report.get('editors_note', '')}")

    print(f"\nFACTS SURVIVING WARSAW GEO-FILTER:")
    for table, counts in report.get("facts_stats", {}).items():
        print(f"  {table:<30} {counts.get('warsaw', 0):>4} / {counts.get('total', 0):>4}")

    if dry_run:
        print("\n[DRY RUN — not saved to DB]")
        bj = report.get("brief_json", {})
        print(f"\nFULL BRIEF JSON (truncated):")
        import json as _json
        sections = bj.get("sections", [])
        for s in sections:
            print(f"\n  [{s.get('id', '?')}] {s.get('title', '')}")
            print(f"  {s.get('body', '')[:300]}...")
    else:
        print(f"\nStored: week_ending={brief_row.week_ending}, id={brief_row.id}")
    print(f"{'=' * 65}\n")
