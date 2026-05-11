"""Warsaw district boundary table for spatial POI resolution.

Stores 18 dzielnice polygon boundaries loaded from OpenStreetMap
(admin_level=9 administrative relations). Used for PostGIS spatial
join to populate warsaw_pois.district.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op

revision: str = "0020"
down_revision: str = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS warsaw_districts (
            id              BIGSERIAL PRIMARY KEY,
            osm_relation_id BIGINT NOT NULL UNIQUE,
            name_canonical  TEXT NOT NULL,
            name_osm        TEXT,
            geometry        geometry(MultiPolygon, 4326) NOT NULL,
            area_sqkm       NUMERIC(8, 3) GENERATED ALWAYS AS (
                                ST_Area(geometry::geography) / 1e6
                            ) STORED,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_warsaw_districts_geom
            ON warsaw_districts USING GIST (geometry)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_warsaw_districts_name
            ON warsaw_districts (name_canonical)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS warsaw_districts CASCADE")
