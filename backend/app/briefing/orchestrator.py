"""Weekly brief orchestrator — Opus 4.6 synthesis.

Entry point: run_weekly_brief()
Called by APScheduler every Sunday at 06:00 UTC.
Also callable manually: python -m app.briefing.orchestrator [YYYY-MM-DD] [--force]

Pipeline:
  1. Build data context from all available tables (REIT, listings, typed facts, news)
  2. Send to Opus 4.6 with ephemeral system-prompt cache
  3. Opus outputs structured JSON only — no markdown prose, no code fences
  4. Merge Opus JSON with authoritative context data into brief_json
  5. Store WeeklyBrief row + LLMCall accounting row
  6. Save brief text to blob storage
  7. Trigger Playwright PDF render

Output format: Option A — Opus emits JSON only; Jinja2 (pdf_render) renders HTML.
No raw JSON ever appears in the rendered PDF.
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

from app.briefing.context import build_brief_context
from app.briefing.pdf_render import render_brief_pdf
from app.core.database import AsyncSessionFactory
from app.core.storage import upload_raw
from app.models.brief import WeeklyBrief
from app.models.llm import LLMCall

log = structlog.get_logger(__name__)

OPUS_MODEL = "claude-opus-4-6"

# USD per 1M tokens
_OPUS_PRICING = {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50}

# ── System prompt: JSON-only analysis schema ─────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior research analyst at White Star, a Saudi Arabia real estate investment fund \
specialising in Riyadh industrial and warehouse property.

Your weekly brief is the authoritative internal view of the market, read by fund partners \
every Sunday before the trading week opens.

Style rules:
- Precise, direct, evidence-based. Never overstate.
- Acknowledge data gaps explicitly — partners trust the brief because it is honest about limits.
- Use SAR for all amounts. Dates in DD MMM YYYY format.
- No marketing language.
- Every cited claim must use the verbatim source_citation text from the fact data (≤15 words).
- Maximum one direct quote per source publication per brief. Paraphrase otherwise.
- Exclude any item about non-KSA geography (Dubai, UAE, Qatar, etc.).

Output format: You must output ONLY a valid JSON object. No prose outside the JSON. \
No markdown code fences. No commentary before or after the JSON. \
Start your response with { and end with }.

JSON schema (all keys required; use null for unavailable data):
{
  "executive_summary": "2-3 sentence string: the single most important signal this week",
  "reit_commentary": "string: analysis of REIT price movements and sector context",
  "reit_data_gaps": ["string"],
  "transaction_commentary": "string: transaction data status and mitigation",
  "transaction_data_gaps": ["string"],
  "warehouse_commentary": "string: analysis of listing prices, rent signals, supply pipeline",
  "warehouse_data_gaps": ["string"],
  "news_intelligence": [
    {
      "headline": "string",
      "score": number,
      "implication": "string: 1-2 sentence market implication for Riyadh industrial RE",
      "citation": "string: verbatim quote ≤15 words from source_citation field, or null",
      "source": "string: publication name",
      "date": "string: DD MMM YYYY or null"
    }
  ],
  "macro_highlights": [
    {
      "indicator": "string",
      "period": "string",
      "value": "string",
      "direction": "string: up|down|flat",
      "implication": "string: 1-sentence implication for Riyadh industrial RE",
      "citation": "string: verbatim ≤15 words or null"
    }
  ],
  "regulatory_highlights": [
    {
      "authority": "string",
      "summary": "string",
      "effective_date": "string or null",
      "implication": "string: 1-sentence implication",
      "citation": "string: verbatim ≤15 words or null"
    }
  ],
  "supply_highlights": [
    {
      "event_type": "string",
      "description": "string",
      "location": "string or null",
      "implication": "string: 1-sentence implication",
      "citation": "string: verbatim ≤15 words or null"
    }
  ],
  "demand_highlights": [
    {
      "sector": "string",
      "metric": "string",
      "value": "string",
      "implication": "string: 1-sentence implication",
      "citation": "string: verbatim ≤15 words or null"
    }
  ],
  "watch_list": [
    {
      "item": "string: specific thing to monitor",
      "trigger": "string: exact condition that would change the market view",
      "timeline": "string: by DD MMM YYYY or 'next week'"
    }
  ]
}

The watch_list must have exactly 3 items with specific trigger conditions.\
"""


_USER_PROMPT_TMPL = """\
Generate the White Star weekly market intelligence brief for the week ending {week_ending_long}.

## REIT MARKET DATA
{reits}

## TRANSACTION DATA
{transactions}

## RENT INDEX (Research Reports)
{rent_index}

## WAREHOUSE LISTINGS (Aqar)
{listings}

## NEWS ARTICLES (Argaam, Logistics ME — KSA-relevant, relevance ≥ 0.5)
{news}

## EXTRACTED FACTS FROM TYPED TABLES
{facts}

## GOVERNMENT TENDERS (Etimad)
{tenders}

## DATA QUALITY NOTES
{data_notes}

---

Now output the JSON analysis object. Focus on Riyadh industrial and warehouse property. \
Synthesise across all data types — the typed facts contain the most granular signals. \
Do not reproduce facts that are not supported by the data above. \
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
    text = raw.strip()
    # Strip accidental code fence
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("brief_json_parse_failed", raw_preview=text[:200])
        return {"executive_summary": text[:500], "_parse_error": True}


def _format_date_long(d: date) -> str:
    return d.strftime("%-d %B %Y")


def _json_safe(obj: Any) -> Any:
    """Recursively convert types not serializable by orjson (e.g. Decimal → float)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    return obj


async def run_weekly_brief(week_ending: date | None = None, force: bool = False) -> WeeklyBrief:
    """Generate and store the weekly brief. Returns the stored WeeklyBrief row.

    Args:
        week_ending: Date to generate for; defaults to today.
        force: If True, delete any existing brief for this date and regenerate.
    """
    if week_ending is None:
        week_ending = date.today()

    log.info("brief_start", week_ending=str(week_ending), force=force)

    async with AsyncSessionFactory() as session:
        if force:
            await session.execute(
                text("DELETE FROM weekly_briefs WHERE week_ending = :d"),
                {"d": week_ending},
            )
            await session.commit()
            log.info("brief_deleted_for_force_regen", week_ending=str(week_ending))

        # Skip if already generated for this week
        existing = await session.execute(
            select(WeeklyBrief).where(WeeklyBrief.week_ending == week_ending)
        )
        if existing.scalar_one_or_none():
            log.info("brief_already_exists", week_ending=str(week_ending))
            return existing.scalar_one()  # type: ignore[return-value]

        # Build data context
        context = await build_brief_context(session, week_ending)
        log.info("brief_context_built", week_ending=str(week_ending))

        # Call Opus 4.6
        from app.core.config import settings

        client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)
        user_msg = _USER_PROMPT_TMPL.format(
            week_ending=week_ending.isoformat(),
            week_ending_long=_format_date_long(week_ending),
            reits=context["reits"],
            transactions=context["transactions"],
            rent_index=context["rent_index"],
            listings=context["listings"],
            news=context["news"],
            facts=context["facts"],
            tenders=context["tenders"],
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
            "brief_generated",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_write=getattr(response.usage, "cache_creation_input_tokens", 0),
            cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
            cost_usd=round(cost, 4),
        )

        # Merge Opus analysis with authoritative context data.
        # Template renders REIT prices from _reit_rows (never from Opus, to prevent hallucination).
        # _json_safe converts Decimal → float so orjson can serialize.
        brief_json: dict[str, Any] = _json_safe({
            **opus_json,
            "_reit_rows": context["_reit_rows"],
            "_listing_stats": context["_listing_stats"],
            "_week_ending": week_ending.isoformat(),
            "_week_ending_long": _format_date_long(week_ending),
            "_model_id": OPUS_MODEL,
            "_cost_usd": round(cost, 6),
            "_input_tokens": response.usage.input_tokens,
            "_output_tokens": response.usage.output_tokens,
        })

        # Store raw Opus response to blob
        raw_bytes = raw_response.encode()
        uri, _ = await upload_raw(
            raw_bytes, "brief", "md",
            content_type="text/plain",
            ts=datetime.now(UTC),
        )

        # Save WeeklyBrief row
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

        # LLM accounting
        session.add(
            LLMCall(
                model_id=OPUS_MODEL,
                prompt_sha=_prompt_sha(),
                task_type="weekly_brief",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
                cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
                cost_usd=cost,
                success=True,
            )
        )

        await session.commit()
        log.info("brief_stored", week_ending=str(week_ending), uri=uri, cost_usd=round(cost, 4))

        # Phase 4b — PDF render
        await render_brief_pdf(brief_row, session)

        return brief_row


if __name__ == "__main__":
    import asyncio
    import sys

    from app.core.logging import configure_logging

    configure_logging()

    args = sys.argv[1:]
    force = "--force" in args
    date_args = [a for a in args if not a.startswith("--")]
    target = date.fromisoformat(date_args[0]) if date_args else date.today()

    brief = asyncio.run(run_weekly_brief(target, force=force))
    print(f"\n{'=' * 60}")
    print(f"Week ending: {brief.week_ending}")
    print(f"Cost: ${brief.cost_usd:.4f} | Tokens: {brief.input_tokens}in / {brief.output_tokens}out")
    print(f"PDF: {brief.pdf_uri}")
    print(f"{'=' * 60}")
