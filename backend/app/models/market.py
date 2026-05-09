"""Core market data models — transactions, listings, REITs, news, tenders.

Data lineage fields on every structured row:
    source_id          — natural key from the originating portal
    raw_uri            — s3:// pointer to the original raw blob
    extracted_at       — when structuring ran (not when data was published)
    extractor_version  — semver tag of the extractor code that produced the row
    prompt_sha         — first 12 chars of the prompt template SHA-256 used by Claude
    model_id           — e.g. "claude-sonnet-4-6"
    confidence         — Claude's self-rated extraction quality (1-5); ≤3 → review queue

Source priority for conflict resolution in the fact_resolved view:
    1 = primary (REGA, Tadawul)
    2 = authoritative secondary (Knight Frank, CBRE, JLL)
    3 = aggregator (Argaam, Mubasher)
    4 = listing portal (Aqar, Bayut, PropertyFinder, Wasalt)
"""

from __future__ import annotations

import enum
from datetime import date, datetime  # noqa: TC003

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Index as SAIndex
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PropertyType(enum.StrEnum):
    warehouse = "warehouse"
    industrial_land = "industrial_land"
    factory = "factory"
    logistics = "logistics"
    office = "office"
    retail = "retail"
    mixed = "mixed"
    residential = "residential"
    other = "other"


class TransactionType(enum.StrEnum):
    sale = "sale"
    lease = "lease"
    mortgage = "mortgage"


class Transaction(Base):
    """REGA / SREM transaction indicator rows — aggregated, not deed-level.

    Deed-level data (buyer/seller names, deed number) is Nafath-gated and
    not collected — that would require PDPL controller registration and
    a transfer impact assessment before being sent to the Anthropic API.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_transactions_source_id"),
        SAIndex("ix_tx_district_date", "district", "transaction_date"),
        SAIndex("ix_tx_ptype_district_date", "property_type", "district", "transaction_date"),
        CheckConstraint("area_sqm > 0", name="ck_tx_positive_area"),
        CheckConstraint("price_sar > 0", name="ck_tx_positive_price"),
        CheckConstraint("confidence BETWEEN 1 AND 5", name="ck_tx_confidence"),
        CheckConstraint("source_priority BETWEEN 1 AND 4", name="ck_tx_source_priority"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    district: Mapped[str] = mapped_column(String(200), nullable=False)
    district_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh")
    region: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh Region")
    property_type: Mapped[str] = mapped_column(
        Enum(PropertyType, name="property_type_enum"), nullable=False
    )
    transaction_type: Mapped[str] = mapped_column(
        Enum(TransactionType, name="transaction_type_enum"),
        nullable=False,
        default=TransactionType.sale,
    )
    area_sqm: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_sar: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # price_per_sqm is a generated column in the DB migration; not mapped here
    # to avoid ORM interference with the GENERATED ALWAYS AS expression.
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Data lineage ---
    source_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source_priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReitSnapshot(Base):
    """Daily price + NAV + distribution snapshot for Tadawul-listed REITs.

    Price comes from yfinance (15-min delayed).
    NAV from CMA-mandated semi-annual valuation reports (parsed PDF).
    Distribution history from Argaam cross-checked against Tadawul dividends calendar.
    FFO is manually computed from annual reports: NetIncome + Depreciation ± ValuationGains.
    Occupancy is a known gap — not systematically disclosed by Saudi REITs.
    """

    __tablename__ = "reit_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", "snapshot_date", name="uq_reit_ticker_date"),
        SAIndex("ix_reit_snap_ticker_date", "ticker", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "4331.SR"
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_sar: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    nav_per_unit_sar: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    # Positive = premium to NAV, negative = discount
    nav_discount_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    ffo_per_unit_sar: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    distribution_per_unit_sar: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    # Implied cap rate: NOI / (total market cap), used for MODON R1 exit comps
    implied_cap_rate_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    occupancy_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Known gap — not systematically disclosed"
    )
    total_assets_sar: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Data lineage ---
    source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Listing(Base):
    """Warehouse / industrial listings from Aqar, Bayut, PropertyFinder, Wasalt.

    Listings are leading indicators — they reflect asking prices before
    transactions close. The gap between listed rent and REGA transaction rent
    is itself an analytical signal.
    """

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("portal", "external_id", name="uq_listing_portal_external_id"),
        SAIndex("ix_listing_portal_district_date", "portal", "district", "listed_at"),
        CheckConstraint("listing_type IN ('sale','lease')", name="ck_listing_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    portal: Mapped[str] = mapped_column(String(50), nullable=False)  # "aqar", "bayut", etc.
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    listing_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "sale" | "lease"
    property_type: Mapped[str] = mapped_column(
        Enum(PropertyType, name="property_type_enum"), nullable=False
    )
    district: Mapped[str] = mapped_column(String(200), nullable=True)
    district_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh")
    area_sqm: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_sar: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # For lease listings: annual rent
    rent_sar_annual: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Data lineage ---
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class NewsArticle(Base):
    """News articles from Argaam, Mubasher, MODON press releases, etc.

    Haiku 4.5 triage scores relevance (0-1) before Sonnet extraction runs.
    Only articles with relevance ≥ 0.5 get structured extraction.
    """

    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_article_source_external_id"),
        SAIndex("ix_article_source_published", "source", "published_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    title_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True, comment="Haiku 4.5 triage score 0.0-1.0"
    )
    structured_facts: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Sonnet-extracted facts: rent movements, transactions, regulatory changes",
    )

    # --- Data lineage ---
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Tender(Base):
    """MODON-related tenders surfaced via the Etimad Developer API."""

    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint("etimad_id", name="uq_tender_etimad_id"),
        SAIndex("ix_tender_entity_published", "entity_name", "published_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    etimad_id: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_sar: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RentIndex(Base):
    """Quarterly rent index observations extracted from research reports and news.

    Source hierarchy (source_priority):
      1 = REGA official data (not yet available)
      2 = Knight Frank / CBRE / JLL reports (most reliable)
      3 = Argaam / news articles
      4 = Aqar / listing portals (asking prices, not transacted)

    Rows from multiple sources for the same (district, property_type, period)
    are resolved by the fact_resolved view using source_priority.
    """

    __tablename__ = "rent_index"
    __table_args__ = (
        UniqueConstraint(
            "district",
            "property_type",
            "period",
            "source",
            name="uq_rent_index_district_type_period_source",
        ),
        SAIndex("ix_rent_idx_district_period", "district", "period"),
        SAIndex("ix_rent_idx_ptype_period", "property_type", "period"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    district: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh")
    property_type: Mapped[str] = mapped_column(
        Enum(PropertyType, name="property_type_enum"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False, comment="e.g. Q4 2024 or 2024")
    rent_sar_sqm_annual: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    yoy_change_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    vacancy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)

    # --- Data lineage ---
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DistrictAlias(Base):
    """Canonical district registry with alias lookup table.

    Knight Frank writes "Al Olaya", REGA uses "العليا", Aqar uses "Olaya District"
    — all three map to the same canonical_id. The canonical source is SPL National
    Address API (api.address.gov.sa), backed by the homaily GeoJSON dataset.
    """

    __tablename__ = "district_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    alias_lang: Mapped[str] = mapped_column(String(10), nullable=False)  # "ar", "en"
    # Source that uses this specific spelling
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Canonical names (on the canonical_id rows)
    name_ar: Mapped[str | None] = mapped_column(String(300), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Riyadh")

    __table_args__ = (
        UniqueConstraint("alias", "source", name="uq_district_alias_source"),
        SAIndex("ix_district_alias_canonical", "canonical_id"),
        SAIndex("ix_district_alias_lookup", "alias"),
    )


class MacroIndicator(Base):
    """Manually-maintained macro indicator table.

    One row per indicator key. Updated weekly by Karol via the admin endpoint
    POST /api/admin/macro-indicators/{key}.

    Automated scraping deferred to a later phase. Until then, source='manual'
    and fetched_at is set to the time of the last manual update.

    Valid keys: sama_repo_rate, sar_usd, brent, saudi_10y_yield, cpi_yoy,
                riyadh_population
    """

    __tablename__ = "macro_indicators"

    indicator_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[float] = mapped_column(Numeric(precision=18, scale=6), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)   # e.g. "2026-Q1"
    source: Mapped[str] = mapped_column(String(200), nullable=False)  # "manual" or publication
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
