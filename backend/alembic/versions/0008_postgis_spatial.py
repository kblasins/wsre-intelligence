"""Phase 3.5 — PostGIS spatial layer.

Adds:
  - PostGIS + topology extensions
  - districts table (canonical district registry with polygon geometry)
  - pois table (OpenStreetMap points of interest)
  - regulatory_zones table (MODON, SEZ, foreign ownership boundaries)
  - reit_properties table (individual REIT property assets with location)
  - saved_sites table (user-saved evaluation geometries)
  - Spatial columns on transactions and listings (location + precision)
  - GIST indexes for all geometry columns

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-18
"""

from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── PostGIS extensions ─────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")

    # ── districts ──────────────────────────────────────────────────────────
    # Canonical district table — one row per district, holds the authoritative
    # polygon. district_aliases remains for name-normalization lookups.
    op.execute("""
        CREATE TABLE IF NOT EXISTS districts (
            id          BIGSERIAL PRIMARY KEY,
            name_en     TEXT NOT NULL,
            name_ar     TEXT,
            city        TEXT NOT NULL DEFAULT 'Riyadh',
            region      TEXT,
            district_code TEXT,
            polygon     geometry(MultiPolygon, 4326),
            area_sqkm   NUMERIC(10,3)
                GENERATED ALWAYS AS
                    (CASE WHEN polygon IS NOT NULL
                          THEN ROUND((ST_Area(polygon::geography) / 1000000)::numeric, 3)
                          ELSE NULL END)
                STORED,
            source      TEXT,
            source_url  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_districts_polygon
            ON districts USING GIST (polygon)
            WHERE polygon IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_districts_city
            ON districts (city)
    """)

    # Derived centroid as a regular index — generated column needs pg15+
    # We store a functional index instead to stay compatible.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_districts_centroid
            ON districts USING GIST (ST_Centroid(polygon))
            WHERE polygon IS NOT NULL
    """)

    # ── pois ───────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS pois (
            id              BIGSERIAL PRIMARY KEY,
            osm_id          BIGINT,
            osm_type        TEXT,
            category        TEXT NOT NULL,
            subcategory     TEXT,
            name_en         TEXT,
            name_ar         TEXT,
            location        geometry(Point, 4326) NOT NULL,
            address         TEXT,
            tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
            source          TEXT NOT NULL DEFAULT 'osm_overpass',
            first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_poi_source_osm UNIQUE (source, osm_id, osm_type)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_pois_location
            ON pois USING GIST (location)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_pois_category
            ON pois (category)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_pois_last_seen
            ON pois (last_seen_at)
    """)

    # ── regulatory_zones ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS regulatory_zones (
            id              BIGSERIAL PRIMARY KEY,
            zone_type       TEXT NOT NULL,
            name_en         TEXT NOT NULL,
            name_ar         TEXT,
            polygon         geometry(MultiPolygon, 4326) NOT NULL,
            rules           JSONB NOT NULL DEFAULT '{}'::jsonb,
            effective_from  DATE,
            effective_to    DATE,
            source          TEXT NOT NULL,
            source_url      TEXT,
            source_citation TEXT,
            last_verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_regzones_polygon
            ON regulatory_zones USING GIST (polygon)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_regzones_type
            ON regulatory_zones (zone_type)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_regzones_effective
            ON regulatory_zones (effective_from, effective_to)
    """)

    # ── reit_properties ────────────────────────────────────────────────────
    # Individual physical assets held by REITs — distinct from reit_snapshots
    # (which are time-series price records). One row per property.
    op.execute("""
        CREATE TABLE IF NOT EXISTS reit_properties (
            id              BIGSERIAL PRIMARY KEY,
            ticker          TEXT NOT NULL,
            property_name   TEXT NOT NULL,
            property_type   TEXT,
            district        TEXT,
            city            TEXT NOT NULL DEFAULT 'Riyadh',
            location        geometry(Point, 4326),
            gfa_sqm         NUMERIC(12,2),
            occupancy_pct   NUMERIC(5,2),
            annual_rent_sar NUMERIC(14,2),
            valuation_sar   NUMERIC(16,2),
            source          TEXT NOT NULL,
            source_url      TEXT,
            extracted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_reit_property UNIQUE (ticker, property_name)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_reit_props_location
            ON reit_properties USING GIST (location)
            WHERE location IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_reit_props_ticker
            ON reit_properties (ticker)
    """)

    # ── saved_sites ────────────────────────────────────────────────────────
    # users.id is UUID (fastapi-users default)
    op.execute("""
        CREATE TABLE IF NOT EXISTS saved_sites (
            id              BIGSERIAL PRIMARY KEY,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            description     TEXT,
            geometry        geometry(Geometry, 4326) NOT NULL,
            asset_class     TEXT,
            target_gfa_sqm  NUMERIC(12,2),
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_saved_sites_geometry
            ON saved_sites USING GIST (geometry)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_saved_sites_user
            ON saved_sites (user_id)
    """)

    # ── spatialize transactions ────────────────────────────────────────────
    op.execute("""
        ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS location geometry(Point, 4326)
    """)

    op.execute("""
        ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS location_precision TEXT
                CHECK (location_precision IN ('exact','address_geocoded','district_centroid'))
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tx_location
            ON transactions USING GIST (location)
            WHERE location IS NOT NULL
    """)

    # ── spatialize listings ────────────────────────────────────────────────
    op.execute("""
        ALTER TABLE listings
            ADD COLUMN IF NOT EXISTS location geometry(Point, 4326)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_listings_location
            ON listings USING GIST (location)
            WHERE location IS NOT NULL
    """)

    # ── isochrone_cache ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS isochrone_cache (
            id          BIGSERIAL PRIMARY KEY,
            center      geometry(Point, 4326) NOT NULL,
            profile     TEXT NOT NULL,
            minutes_15  geometry(Polygon, 4326),
            minutes_30  geometry(Polygon, 4326),
            minutes_60  geometry(Polygon, 4326),
            provider    TEXT NOT NULL DEFAULT 'openrouteservice',
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_isochrone_center_profile UNIQUE (center, profile)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_isochrone_center
            ON isochrone_cache USING GIST (center)
    """)

    # ── evaluate_cache ─────────────────────────────────────────────────────
    # Caches full site evaluation bundles by sha256 of request params.
    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluate_cache (
            cache_key   TEXT PRIMARY KEY,
            geometry_wkt TEXT NOT NULL,
            radius_m    INTEGER NOT NULL DEFAULT 5000,
            asset_class TEXT,
            time_window_days INTEGER NOT NULL DEFAULT 90,
            result      JSONB NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at  TIMESTAMPTZ NOT NULL
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_eval_cache_expires
            ON evaluate_cache (expires_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluate_cache CASCADE")
    op.execute("DROP TABLE IF EXISTS isochrone_cache CASCADE")
    op.execute("DROP TABLE IF EXISTS saved_sites CASCADE")
    op.execute("DROP TABLE IF EXISTS reit_properties CASCADE")
    op.execute("DROP TABLE IF EXISTS regulatory_zones CASCADE")
    op.execute("DROP TABLE IF EXISTS pois CASCADE")
    op.execute("DROP TABLE IF EXISTS districts CASCADE")

    op.execute("""
        ALTER TABLE listings
            DROP COLUMN IF EXISTS location
    """)

    op.execute("""
        ALTER TABLE transactions
            DROP COLUMN IF EXISTS location_precision,
            DROP COLUMN IF EXISTS location
    """)

    # Do not drop PostGIS — other schema objects may depend on it.
