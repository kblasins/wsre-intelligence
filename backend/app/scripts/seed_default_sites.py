"""Seed default saved sites for the admin user.

Usage:
    cd backend && python -m app.scripts.seed_default_sites

Inserts MODON Riyadh 1st Industrial City as a saved site for the admin user.
Safe to re-run — idempotent (skips if a site with the same name already exists
for that user).

Geometry source: same approximate polygon as migration 0011 (regulatory_zones).
Accuracy: LOW — simplified rectangle covering the approximate footprint.
Do not use for legal or leasing boundary decisions.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging

log = structlog.get_logger(__name__)

# Approximate boundary for MODON Riyadh 1st Industrial City.
# Source: MODON public portal + OSM Relation #2900093 (simplified, confidence=low).
# Centre: 24.712°N, 46.772°E
_MODON_R1_GEOJSON = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [46.748, 24.698],
        [46.797, 24.698],
        [46.797, 24.727],
        [46.762, 24.730],
        [46.748, 24.722],
        [46.748, 24.698],
    ]],
})

_DEFAULT_SITES = [
    {
        "name": "MODON Riyadh 1st Industrial City",
        "description": (
            "First Industrial City, Riyadh (Al-Malaz / Al-Naseem corridor). "
            "Approximate boundary — confidence: low. "
            "Authoritative boundaries available from modon.gov.sa."
        ),
        "geometry_geojson": _MODON_R1_GEOJSON,
        "asset_class": "warehouse",
        "notes": (
            "Boundary approximated from public MODON publications and "
            "OSM Relation #2900093. Use for orientation only."
        ),
    },
]


async def seed_default_sites() -> None:
    configure_logging()

    async with AsyncSessionFactory() as session:
        # Look up admin user by email
        result = await session.execute(
            text("SELECT id FROM \"user\" WHERE email = :email LIMIT 1"),
            {"email": settings.admin_email},
        )
        row = result.mappings().first()
        if not row:
            log.error(
                "admin_user_not_found",
                email=settings.admin_email,
                hint="Run 'make seed-admin' first.",
            )
            return

        admin_id = str(row["id"])
        now = datetime.now(UTC)

        for site in _DEFAULT_SITES:
            # Check if already seeded
            exists = await session.execute(
                text(
                    "SELECT id FROM saved_sites WHERE user_id = :uid AND name = :name LIMIT 1"
                ),
                {"uid": admin_id, "name": site["name"]},
            )
            if exists.first():
                log.info("default_site_already_exists", name=site["name"])
                continue

            await session.execute(
                text("""
                    INSERT INTO saved_sites
                        (user_id, name, description, geometry,
                         asset_class, notes, created_at, updated_at)
                    VALUES
                        (:uid, :name, :desc,
                         ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326),
                         :asset_class, :notes, :now, :now)
                """),
                {
                    "uid": admin_id,
                    "name": site["name"],
                    "desc": site["description"],
                    "geojson": site["geometry_geojson"],
                    "asset_class": site["asset_class"],
                    "notes": site["notes"],
                    "now": now,
                },
            )
            log.info("default_site_seeded", name=site["name"])

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_default_sites())
