"""PDF fact extractor — Phase 2 pipeline for Knight Frank / CBRE / JLL reports.

Pipeline:
  1. pymupdf4llm   → Markdown text (fast, free, handles most pages)
  2. Sonnet 4.6    → structured JSON facts (rent indices, transaction counts, forecasts)

The extractor is called by the outbox reconciler when it sees a
knight_frank blob with structured=0.

Entry point: extract_from_blob(session, raw_bytes, outbox_row)
Also callable standalone: python -m app.pdf.extractor <path/to/report.pdf>
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import structlog
from anthropic import AsyncAnthropic

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ingestion import RawIngestOutbox

log = structlog.get_logger(__name__)

SONNET_MODEL = "claude-sonnet-4-6"
MAX_PDF_CHARS = 60_000  # ~15k tokens; Sonnet 200k context gives plenty of headroom

_SYSTEM = """\
You are a structured data extractor for a Saudi Arabia industrial real estate intelligence system.

Extract only facts explicitly stated in the document. Do not invent data. \
If a field is not mentioned, use null or an empty array. \
Respond ONLY with valid JSON — no prose, no markdown, no code fences.\
"""

_USER_TMPL = """\
Extract structured market intelligence from this research report.

SOURCE: {source_slug}
CONTENT:
{content}

Return JSON matching this schema exactly:
{{
  "report_title": "<str or null>",
  "report_date": "<YYYY-MM-DD or null>",
  "author": "<str or null>",
  "market_summary": "<1-3 sentence summary of key industrial/warehouse findings, or null>",
  "rent_indices": [
    {{
      "district": "<str or null>",
      "property_type": "<warehouse|industrial_land|factory|logistics>",
      "rent_sar_sqm_annual": <float or null>,
      "period": "<str e.g. Q4 2024>",
      "yoy_change_pct": <float or null>
    }}
  ],
  "vacancy_rates": [
    {{
      "district": "<str or null>",
      "property_type": "<str>",
      "vacancy_pct": <float or null>,
      "period": "<str or null>"
    }}
  ],
  "supply_pipeline": [
    {{
      "location": "<str or null>",
      "area_sqm": <float or null>,
      "completion_date": "<str or null>",
      "developer": "<str or null>"
    }}
  ],
  "transaction_stats": [
    {{
      "period": "<str>",
      "property_type": "<str>",
      "volume_count": <int or null>,
      "total_value_sar": <float or null>
    }}
  ],
  "key_quotes": [
    "<verbatim sentence from the report containing a market insight>"
  ],
  "confidence": <1-5>
}}\
"""


def _prompt_sha() -> str:
    return hashlib.sha256((_SYSTEM + _USER_TMPL).encode()).hexdigest()[:12]


def _pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to Markdown text using pymupdf4llm."""
    import os
    import tempfile

    import pymupdf4llm  # type: ignore[import-untyped]

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        md = pymupdf4llm.to_markdown(tmp_path)
    finally:
        os.unlink(tmp_path)

    return md


async def _extract_facts(
    client: AsyncAnthropic,
    content: str,
    source_slug: str,
) -> dict[str, Any]:
    """Call Sonnet 4.6 to extract structured facts from report markdown."""
    user_msg = _USER_TMPL.format(
        source_slug=source_slug,
        content=content[:MAX_PDF_CHARS],
    )

    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    try:
        facts = json.loads(raw)
        if not isinstance(facts, dict):
            raise ValueError("not a dict")
    except (json.JSONDecodeError, ValueError):
        log.warning("pdf_extract_parse_failed", raw=raw[:300])
        facts = {"_raw_response": raw[:1000], "confidence": 1}

    return facts, response.usage


async def extract_from_blob(
    session: AsyncSession,
    raw_bytes: bytes,
    outbox_row: RawIngestOutbox,
) -> None:
    """Reconciler entry point — extract facts from a stored PDF blob.

    Writes results into the outbox row's scraper_meta and upserts
    any discovered rent index rows.
    """
    from sqlalchemy import update

    from app.core.config import settings
    from app.models.ingestion import RawIngestOutbox as _OB
    from app.models.llm import LLMCall

    slug = outbox_row.scraper_meta.get("slug", "unknown")
    log.info("pdf_extractor_start", slug=slug, size_bytes=len(raw_bytes))

    try:
        markdown_text = _pdf_to_markdown(raw_bytes)
    except Exception as exc:
        log.error("pdf_to_markdown_failed", slug=slug, error=str(exc))
        raise

    client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)

    try:
        facts, usage = await _extract_facts(client, markdown_text, slug)
    except Exception as exc:
        log.error("pdf_llm_failed", slug=slug, error=str(exc))
        raise

    from app.core.database import AsyncSessionFactory

    async with AsyncSessionFactory() as db_session:
        # LLM call accounting
        from app.ingestion.extractors.news import _compute_cost

        cost = _compute_cost(usage, SONNET_MODEL)
        db_session.add(
            LLMCall(
                model_id=SONNET_MODEL,
                prompt_sha=_prompt_sha(),
                task_type="pdf_extraction",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0),
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
                cost_usd=cost,
                success=True,
            )
        )

        # Write facts back into outbox meta (no separate facts table yet)
        await db_session.execute(
            update(_OB)
            .where(_OB.id == outbox_row.id)
            .values(
                scraper_meta={
                    **outbox_row.scraper_meta,
                    "extracted_facts": facts,
                    "markdown_chars": len(markdown_text),
                }
            )
        )
        await db_session.commit()

    # Promote extracted rent indices into the typed fact table
    promoted = 0
    try:
        from app.structuring.pdf import promote_pdf_facts

        async with AsyncSessionFactory() as promote_session:
            promoted = await promote_pdf_facts(promote_session, outbox_row)
            await promote_session.commit()
    except Exception as exc:
        log.warning("pdf_promote_failed", slug=slug, error=str(exc))

    log.info(
        "pdf_extractor_done",
        slug=slug,
        confidence=facts.get("confidence"),
        rent_indices=len(facts.get("rent_indices", [])),
        promoted_rows=promoted,
        cost_usd=round(cost, 4),
    )


if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    from app.core.logging import configure_logging

    configure_logging()

    if len(sys.argv) < 2:
        print("Usage: python -m app.pdf.extractor <path/to/report.pdf>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    async def _main() -> None:
        from app.core.config import settings

        client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)
        md = _pdf_to_markdown(pdf_path.read_bytes())
        print(f"Markdown length: {len(md):,} chars")
        facts, usage = await _extract_facts(client, md, pdf_path.stem)
        print(json.dumps(facts, indent=2, ensure_ascii=False))
        print(f"\nTokens: {usage.input_tokens}in / {usage.output_tokens}out")

    asyncio.run(_main())
