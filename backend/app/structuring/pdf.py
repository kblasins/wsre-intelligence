"""PDF structuring pipeline — promotes extracted facts into typed fact tables.

Called by the outbox reconciler after app.pdf.extractor has populated
outbox_row.scraper_meta["extracted_facts"]. Writes RentIndex rows from
the rent_indices array in the extracted facts JSON.

Confidence gate: if the overall extraction confidence is < 4, a ReviewQueue
row is written so a human can verify the facts before they are trusted.

Entry point: promote_pdf_facts(session, outbox_row)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from app.models.market import RentIndex

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ingestion import RawIngestOutbox

log = structlog.get_logger(__name__)

# Map common variant spellings from LLM output to canonical enum values
_PTYPE_MAP: dict[str, str] = {
    "warehouse": "warehouse",
    "warehouses": "warehouse",
    "industrial land": "industrial_land",
    "industrial_land": "industrial_land",
    "factory": "factory",
    "factories": "factory",
    "logistics": "logistics",
    "logistics facility": "logistics",
    "office": "office",
    "retail": "retail",
    "mixed": "mixed",
    "residential": "residential",
}


def _normalize_ptype(raw: str | None) -> str:
    if not raw:
        return "warehouse"
    return _PTYPE_MAP.get(raw.strip().lower(), "warehouse")


def _parse_period(raw: str | None) -> str | None:
    """Normalize period strings: 'Q4 2024', '2024', 'H2 2024', etc."""
    if not raw:
        return None
    s = raw.strip()
    # Accept Q1-Q4 YYYY, H1/H2 YYYY, YYYY
    import re

    if re.match(r"^[QH]\d\s+\d{4}$", s):
        return s
    if re.match(r"^\d{4}$", s):
        return s
    # e.g. "Fourth Quarter 2024" → keep as-is (Sonnet should produce clean strings)
    return s[:20]


async def promote_pdf_facts(
    session: AsyncSession,
    outbox_row: RawIngestOutbox,
) -> int:
    """Write RentIndex rows from extracted_facts in outbox_row.scraper_meta.

    Returns the number of rows upserted.
    """
    facts: dict[str, Any] = outbox_row.scraper_meta.get("extracted_facts", {})
    if not facts:
        log.warning("promote_pdf_facts_no_facts", outbox_id=outbox_row.id)
        return 0

    source = outbox_row.source  # "knight_frank", "cbre", "jll"
    # Priority mapping matches source_registry
    priority_map = {"knight_frank": 2, "cbre": 2, "jll": 2, "rega": 1}
    source_priority = priority_map.get(source, 2)

    raw_uri = outbox_row.raw_uri
    model_id = outbox_row.scraper_meta.get("model_id")
    prompt_sha = outbox_row.scraper_meta.get("prompt_sha")
    now = datetime.now(UTC)

    rent_indices: list[dict[str, Any]] = facts.get("rent_indices", [])
    count = 0

    for item in rent_indices:
        period = _parse_period(item.get("period"))
        rent = item.get("rent_sar_sqm_annual")
        ptype_raw = item.get("property_type", "warehouse")

        if not period:
            log.debug("promote_pdf_skip_no_period", item=str(item)[:100])
            continue
        if rent is not None and (float(rent) <= 0 or float(rent) > 10_000):
            log.debug("promote_pdf_skip_implausible_rent", rent=rent)
            continue

        row = {
            "district": item.get("district"),
            "city": "Riyadh",
            "property_type": _normalize_ptype(ptype_raw),
            "period": period,
            "rent_sar_sqm_annual": float(rent) if rent is not None else None,
            "yoy_change_pct": float(item["yoy_change_pct"]) if item.get("yoy_change_pct") else None,
            "vacancy_pct": None,  # not in rent_indices (separate array)
            "source": source,
            "source_priority": source_priority,
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
                set_={
                    "rent_sar_sqm_annual": row["rent_sar_sqm_annual"],
                    "yoy_change_pct": row["yoy_change_pct"],
                    "extracted_at": now,
                },
            )
        )
        await session.execute(stmt)
        count += 1

    # Also pull vacancy rates from vacancy_rates array
    for item in facts.get("vacancy_rates", []):
        period = _parse_period(item.get("period"))
        vac = item.get("vacancy_pct")
        if not period or vac is None:
            continue

        row = {
            "district": item.get("district"),
            "city": "Riyadh",
            "property_type": _normalize_ptype(item.get("property_type", "warehouse")),
            "period": period,
            "rent_sar_sqm_annual": None,
            "yoy_change_pct": None,
            "vacancy_pct": float(vac),
            "source": source,
            "source_priority": source_priority,
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
                set_={"vacancy_pct": float(vac), "extracted_at": now},
            )
        )
        await session.execute(stmt)
        count += 1

    # Confidence gate — write to review queue if extraction quality is below threshold
    confidence = facts.get("confidence")
    if isinstance(confidence, int) and confidence <= 3:
        from app.models.review import ReviewQueue

        uncertain = [
            k for k, v in facts.items()
            if v is None or (v == [] and k not in ("confidence", "key_quotes"))
        ]
        session.add(
            ReviewQueue(
                source_table="raw_ingest_outbox",
                source_row_id=outbox_row.id,
                raw_uri=outbox_row.raw_uri,
                model_id=model_id,
                prompt_sha=prompt_sha,
                confidence=confidence,
                llm_output=facts,
                uncertain_fields=uncertain,
            )
        )
        log.warning(
            "promote_pdf_low_confidence",
            source=source,
            confidence=confidence,
            outbox_id=outbox_row.id,
        )

    log.info("promote_pdf_facts_done", source=source, rows=count, outbox_id=outbox_row.id)
    return count
