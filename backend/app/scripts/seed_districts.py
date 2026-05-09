"""Riyadh industrial district seed — DistrictAlias table.

Populates canonical industrial/warehouse districts in Riyadh with their
common EN/AR spellings as used by Knight Frank, REGA, Aqar, and MODON.

Usage:
    cd backend && python -m app.scripts.seed_districts

Idempotent: skips rows that already exist (unique constraint on alias+source).
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging
from app.models.market import DistrictAlias

log = structlog.get_logger(__name__)

# canonical_id → (name_en, name_ar, aliases)
# aliases: list of (alias, alias_lang, source | None)
_DISTRICTS: list[dict] = [
    {
        "canonical_id": 1,
        "name_en": "Second Industrial City",
        "name_ar": "المدينة الصناعية الثانية",
        "city": "Riyadh",
        "aliases": [
            ("Second Industrial City", "en", None),
            ("Second Industrial City Riyadh", "en", "knight_frank"),
            ("المدينة الصناعية الثانية", "ar", None),
            ("المدينة الصناعية 2", "ar", "aqar"),
            ("2nd Industrial", "en", "modon"),
        ],
    },
    {
        "canonical_id": 2,
        "name_en": "Third Industrial City",
        "name_ar": "المدينة الصناعية الثالثة",
        "city": "Riyadh",
        "aliases": [
            ("Third Industrial City", "en", None),
            ("المدينة الصناعية الثالثة", "ar", None),
            ("3rd Industrial", "en", "modon"),
            ("المدينة الصناعية 3", "ar", "aqar"),
        ],
    },
    {
        "canonical_id": 3,
        "name_en": "Al Kharj Road Industrial",
        "name_ar": "صناعية طريق الخرج",
        "city": "Riyadh",
        "aliases": [
            ("Al Kharj Road Industrial", "en", None),
            ("Kharj Road", "en", "knight_frank"),
            ("صناعية طريق الخرج", "ar", None),
            ("طريق الخرج", "ar", "aqar"),
        ],
    },
    {
        "canonical_id": 4,
        "name_en": "Snaiya",
        "name_ar": "صناعية",
        "city": "Riyadh",
        "aliases": [
            ("Snaiya", "en", None),
            ("صناعية", "ar", None),
            ("Sanaiya", "en", "aqar"),
        ],
    },
    {
        "canonical_id": 5,
        "name_en": "Al Dar Al Baida Industrial",
        "name_ar": "الدار البيضاء الصناعية",
        "city": "Riyadh",
        "aliases": [
            ("Al Dar Al Baida Industrial", "en", None),
            ("Dar Al Baida", "en", "knight_frank"),
            ("الدار البيضاء الصناعية", "ar", None),
            ("الدار البيضاء", "ar", "aqar"),
        ],
    },
    {
        "canonical_id": 6,
        "name_en": "Al Sulay",
        "name_ar": "السليّ",
        "city": "Riyadh",
        "aliases": [
            ("Al Sulay", "en", None),
            ("Sulai", "en", "knight_frank"),
            ("السليّ", "ar", None),
            ("السلي", "ar", "aqar"),
        ],
    },
    {
        "canonical_id": 7,
        "name_en": "Jax District (Logistics)",
        "name_ar": "حي جاكس",
        "city": "Riyadh",
        "aliases": [
            ("Jax District", "en", None),
            ("JAX", "en", "modon"),
            ("حي جاكس", "ar", None),
        ],
    },
    {
        "canonical_id": 8,
        "name_en": "KAFD Logistics Zone",
        "name_ar": "مركز الملك عبدالله المالي - لوجستي",
        "city": "Riyadh",
        "aliases": [
            ("KAFD Logistics Zone", "en", None),
            ("KAFD", "en", "knight_frank"),
            ("مركز الملك عبدالله المالي", "ar", None),
        ],
    },
    {
        "canonical_id": 9,
        "name_en": "Takhassusi Industrial",
        "name_ar": "صناعية التخصصي",
        "city": "Riyadh",
        "aliases": [
            ("Takhassusi Industrial", "en", None),
            ("صناعية التخصصي", "ar", None),
        ],
    },
    {
        "canonical_id": 10,
        "name_en": "Al Aziziyah",
        "name_ar": "العزيزية",
        "city": "Riyadh",
        "aliases": [
            ("Al Aziziyah", "en", None),
            ("Aziziyah", "en", "aqar"),
            ("العزيزية", "ar", None),
        ],
    },
]


async def seed_districts() -> None:
    configure_logging()

    async with AsyncSessionFactory() as session:
        inserted = 0
        skipped = 0

        for district in _DISTRICTS:
            for alias, alias_lang, source in district["aliases"]:
                stmt = (
                    pg_insert(DistrictAlias)
                    .values(
                        canonical_id=district["canonical_id"],
                        alias=alias,
                        alias_lang=alias_lang,
                        source=source,
                        name_en=district["name_en"],
                        name_ar=district["name_ar"],
                        city=district["city"],
                    )
                    .on_conflict_do_nothing(constraint="uq_district_alias_source")
                )
                result = await session.execute(stmt)
                if result.rowcount:
                    inserted += 1
                else:
                    skipped += 1

        await session.commit()
        log.info("districts_seeded", inserted=inserted, skipped=skipped)
        print(f"Done — {inserted} rows inserted, {skipped} already existed.")


if __name__ == "__main__":
    asyncio.run(seed_districts())
