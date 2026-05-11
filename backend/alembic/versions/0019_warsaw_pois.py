"""Warsaw POI table for Workbench map layers.

Stores OpenStreetMap points of interest for Warsaw, organised by
category (school, healthcare, park, metro_station, tram_stop, rail_station).
Separate from the Saudi-focused `pois` table in 0008.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op

revision: str = "0019"
down_revision: str = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS warsaw_pois (
            id              BIGSERIAL PRIMARY KEY,
            osm_id          BIGINT NOT NULL,
            osm_type        TEXT NOT NULL,
            category        TEXT NOT NULL,
            subcategory     TEXT,
            name            TEXT,
            name_pl         TEXT,
            name_en         TEXT,
            address         TEXT,
            district        TEXT,
            coordinates     geometry(Point, 4326) NOT NULL,
            boundary        geometry(Geometry, 4326),
            tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_warsaw_poi_osm UNIQUE (osm_id, osm_type)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_warsaw_pois_category
            ON warsaw_pois (category)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_warsaw_pois_district
            ON warsaw_pois (district)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_warsaw_pois_coords
            ON warsaw_pois USING GIST (coordinates)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_warsaw_pois_boundary
            ON warsaw_pois USING GIST (boundary)
            WHERE boundary IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS warsaw_pois CASCADE")
