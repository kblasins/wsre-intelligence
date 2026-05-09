"""Seed MODON Riyadh 1st Industrial City regulatory zone.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-18

Seeds one row in regulatory_zones for the MODON Riyadh 1st Industrial City
(المدينة الصناعية الأولى بالرياض), located in the Al-Malaz / Al-Naseem
corridor, northeast Riyadh.

Polygon source: approximate boundary derived from publicly available MODON
publications and OpenStreetMap data (OSM Relation #2900093).
Accuracy: LOW — the polygon is a simplified rectangle that covers the
approximate footprint. Do not use for legal or leasing boundary decisions.

Additional zones will be added once authoritative polygon sources (MODON
GIS data, Royal Commission shapefiles) are available.

Confidence is recorded in the rules JSONB as {"confidence": "low"}.
"""

from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None

# Approximate polygon for MODON Riyadh 1st Industrial City.
# Source: MODON public portal + OSM Relation #2900093 (simplified).
# CRS: WGS-84 (SRID 4326), coordinates in (longitude, latitude) order.
#
# The zone covers roughly 10 km² in the Al-Malaz / Al-Naseem area.
# Centre point approximately: 24.712°N, 46.772°E
_POLYGON_WKT = (
    "SRID=4326;MULTIPOLYGON(("
    "("
    "46.748 24.698, "
    "46.797 24.698, "
    "46.797 24.727, "
    "46.762 24.730, "
    "46.748 24.722, "
    "46.748 24.698"
    ")"
    "))"
)

_RULES = {
    "confidence": "low",
    "boundary_accuracy": "approximate",
    "zone_class": "industrial",
    "operator": "MODON",
    "permitted_uses": ["manufacturing", "warehousing", "logistics", "light_industrial"],
    "restrictions": ["no_residential", "modon_tenant_licence_required"],
    "notes": (
        "Approximate boundary only. Authoritative boundaries available from "
        "MODON directly (modon.gov.sa) or via ESRI Saudi Arabia GIS portal."
    ),
}

def upgrade() -> None:
    rules_json = json.dumps(_RULES).replace("'", "''")  # escape for SQL literal
    op.execute(
        text(
            f"""
            INSERT INTO regulatory_zones
                (zone_type, name_en, name_ar, polygon, rules,
                 effective_from, source, source_url, source_citation,
                 last_verified_at, created_at)
            VALUES
                (
                    'modon_industrial',
                    'MODON Riyadh 1st Industrial City',
                    'المدينة الصناعية الأولى بالرياض',
                    ST_MakeValid(ST_GeomFromEWKT('{_POLYGON_WKT}')),
                    '{rules_json}'::jsonb,
                    '2000-01-01',
                    'modon_public_approximate',
                    'https://modon.gov.sa/en/IndustrialCities/Pages/Riyadh.aspx',
                    'MODON public portal + OSM Relation #2900093 (simplified, confidence=low)',
                    NOW(),
                    NOW()
                )
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM regulatory_zones WHERE source = 'modon_public_approximate'"
    )
