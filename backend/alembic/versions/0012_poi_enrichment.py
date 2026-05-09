"""POI enrichment — first-class tag columns, polygon geometry, district FK.

Adds:
- operator, brand, phone, website, opening_hours (text)
- building_levels (integer), height_m (numeric 6,2), capacity (integer)
- geometry column (Geometry, SRID 4326) for original polygon
- footprint_area_sqm (numeric 12,2)
- is_polygon (boolean)
- district_id (FK → districts.id, nullable)
- composite index (district_id, category, subcategory)

Backfills all new columns from existing tags JSONB and spatial lookup.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New scalar columns ─────────────────────────────────────────────────
    op.add_column("pois", sa.Column("operator",       sa.Text,              nullable=True))
    op.add_column("pois", sa.Column("brand",          sa.Text,              nullable=True))
    op.add_column("pois", sa.Column("phone",          sa.Text,              nullable=True))
    op.add_column("pois", sa.Column("website",        sa.Text,              nullable=True))
    op.add_column("pois", sa.Column("opening_hours",  sa.Text,              nullable=True))
    op.add_column("pois", sa.Column("building_levels",sa.Integer,           nullable=True))
    op.add_column("pois", sa.Column("height_m",       sa.Numeric(6, 2),     nullable=True))
    op.add_column("pois", sa.Column("capacity",       sa.Integer,           nullable=True))

    # ── Polygon geometry columns ───────────────────────────────────────────
    op.execute(text("""
        ALTER TABLE pois
          ADD COLUMN IF NOT EXISTS geometry  geometry(Geometry, 4326),
          ADD COLUMN IF NOT EXISTS footprint_area_sqm numeric(12,2),
          ADD COLUMN IF NOT EXISTS is_polygon boolean NOT NULL DEFAULT false
    """))

    # ── District FK ───────────────────────────────────────────────────────
    op.add_column("pois", sa.Column("district_id", sa.BigInteger, sa.ForeignKey("districts.id"), nullable=True))

    # ── Composite index ───────────────────────────────────────────────────
    op.create_index("ix_pois_district_cat_subcat", "pois", ["district_id", "category", "subcategory"])

    # ── Backfill scalar tags from JSONB ───────────────────────────────────
    op.execute(text("""
        UPDATE pois SET
            operator = COALESCE(
                tags->>'operator', tags->>'operator:en', tags->>'brand', tags->>'brand:en'
            ),
            brand = COALESCE(tags->>'brand', tags->>'brand:en'),
            phone = COALESCE(tags->>'phone', tags->>'contact:phone'),
            website = COALESCE(tags->>'website', tags->>'contact:website'),
            opening_hours = tags->>'opening_hours',
            building_levels = (
                CASE
                    WHEN tags->>'building:levels' ~ '^[0-9]+$'
                    THEN (tags->>'building:levels')::integer
                    ELSE NULL
                END
            ),
            height_m = (
                CASE
                    WHEN regexp_replace(COALESCE(tags->>'height',''), '[^0-9.]','','g') ~ '^[0-9]+(\.[0-9]+)?$'
                    THEN regexp_replace(COALESCE(tags->>'height',''), '[^0-9.]','','g')::numeric
                    ELSE NULL
                END
            ),
            capacity = (
                CASE
                    WHEN tags->>'capacity' ~ '^[0-9]+$'
                    THEN (tags->>'capacity')::integer
                    ELSE NULL
                END
            )
        WHERE tags IS NOT NULL AND tags != '{}'::jsonb
    """))

    # ── Backfill district_id from spatial containment ─────────────────────
    op.execute(text("""
        UPDATE pois p
        SET district_id = d.id
        FROM districts d
        WHERE ST_Within(p.location, d.polygon)
          AND d.polygon IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_index("ix_pois_district_cat_subcat", table_name="pois")
    op.drop_column("pois", "district_id")
    op.drop_column("pois", "is_polygon")
    op.drop_column("pois", "footprint_area_sqm")
    op.drop_column("pois", "geometry")
    op.drop_column("pois", "capacity")
    op.drop_column("pois", "height_m")
    op.drop_column("pois", "building_levels")
    op.drop_column("pois", "opening_hours")
    op.drop_column("pois", "website")
    op.drop_column("pois", "phone")
    op.drop_column("pois", "brand")
    op.drop_column("pois", "operator")
