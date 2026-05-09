"""SQLAlchemy ORM models for the Phase 3.5 spatial layer.

Requires PostGIS and geoalchemy2. All geometry columns use SRID 4326 (WGS-84).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class District(Base):
    """Canonical district registry — one row per Riyadh district.

    Holds the authoritative polygon (from SPL / homaily GeoJSON).
    Name normalisation lives in district_aliases; this table is the anchor.
    """

    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh")
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # polygon stored as WKB via GeoAlchemy2; None until loaded from source
    polygon: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    # area_sqkm is a GENERATED ALWAYS column — read-only from Python
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class POI(Base):
    """Point of Interest — sourced from OpenStreetMap via Overpass API."""

    __tablename__ = "pois"
    __table_args__ = (
        UniqueConstraint("source", "osm_id", "osm_type", name="uq_poi_source_osm"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    osm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    osm_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # node/way/relation
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="osm_overpass")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    # ── Enriched tag columns ───────────────────────────────────────────────
    operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    building_levels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_m: Mapped[Any | None] = mapped_column(Numeric(6, 2), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ── Polygon geometry ───────────────────────────────────────────────────
    geometry: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="Geometry", srid=4326), nullable=True
    )
    footprint_area_sqm: Mapped[Any | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_polygon: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ── District ───────────────────────────────────────────────────────────
    district_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("districts.id"), nullable=True, index=True
    )


class RegulatoryZone(Base):
    """Regulatory / planning zone with polygon boundary and rules metadata.

    Human-curated only. Never auto-extracted from news.
    """

    __tablename__ = "regulatory_zones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    zone_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    polygon: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False
    )
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    effective_from: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class REITProperty(Base):
    """Individual physical property asset held by a REIT.

    Separate from reit_snapshots (time-series price data).
    """

    __tablename__ = "reit_properties"
    __table_args__ = (
        UniqueConstraint("ticker", "property_name", name="uq_reit_property"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    property_name: Mapped[str] = mapped_column(Text, nullable=False)
    property_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh")
    location: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    gfa_sqm: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    occupancy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    annual_rent_sar: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    valuation_sar: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class SavedSite(Base):
    """User-saved site geometry for repeated evaluation.

    geometry can be a Point (pin drop) or Polygon (drawn boundary).
    user_id references users.id (UUID from fastapi-users).
    """

    __tablename__ = "saved_sites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False
    )
    asset_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_gfa_sqm: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class IsochroneCache(Base):
    """Cached drive-time isochrone polygons from OpenRouteService.

    Cache key is (center rounded to 3dp, profile). Entries expire after 90 days.
    """

    __tablename__ = "isochrone_cache"
    __table_args__ = (
        UniqueConstraint("center", "profile", name="uq_isochrone_center_profile"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    center: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    profile: Mapped[str] = mapped_column(String(50), nullable=False)  # driving-car / driving-hgv
    minutes_15: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )
    minutes_30: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )
    minutes_60: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="openrouteservice"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class EvaluateCache(Base):
    """Full site evaluation bundle cached by sha256 of request parameters."""

    __tablename__ = "evaluate_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    geometry_wkt: Mapped[str] = mapped_column(Text, nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    asset_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    time_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
