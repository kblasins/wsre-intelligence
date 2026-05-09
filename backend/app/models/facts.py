"""Structured fact tables extracted from news articles by Sonnet.

Each table holds one class of signal extracted from news_articles. Every row
has consistent data-lineage columns and a source_citation (verbatim quote ≤15
words from the article that directly supports the fact).

Routing:
  confidence >= 4  → promoted directly to this table
  confidence <= 3  → review_queue (with source_table pointing here)

All tables reference news_articles.id via article_id (not a FK constraint, to
allow the article to be deleted/re-scraped without cascade deleting facts).
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import BigInteger, DateTime, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplyEvent(Base):
    """New projects, construction starts, completions, land allocations."""

    __tablename__ = "supply_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    event_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="new_development|construction_start|completion|permit|land_allocation"
    )
    developer: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    district_guess: Mapped[str | None] = mapped_column(String(200), nullable=True)
    asset_class: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="warehouse|industrial|office|mixed|residential|infrastructure"
    )
    gfa_sqm: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    land_area_sqm: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    value_sar: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    expected_completion_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    anchor_tenants: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RegulatoryEvent(Base):
    """Regulatory actions: new laws, amendments, enforcement, licensing changes."""

    __tablename__ = "regulatory_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    event_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="new_law|amendment|consultation_open|enforcement_action|licensing_change"
    )
    authority: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scope: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="nationwide|region|asset_class"
    )
    effective_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MacroSignal(Base):
    """Macro-economic indicators with real estate linkage."""

    __tablename__ = "macro_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    indicator: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="building_permits|construction_cost_index|property_price_index|SAMA_rate|inflation|GDP_construction|PIF_allocation"
    )
    period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(16, 4), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="up|down|flat")
    magnitude: Mapped[str | None] = mapped_column(String(100), nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DemandSignal(Base):
    """Demand-side signals: e-commerce volumes, logistics stats, tenant activity."""

    __tablename__ = "demand_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    sector: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="e_commerce|logistics|manufacturing|retail|hospitality|office"
    )
    metric: Mapped[str | None] = mapped_column(String(200), nullable=True)
    period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    value: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="stored as text to handle mixed units")
    geography: Mapped[str | None] = mapped_column(String(200), nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CapitalMarketsEvent(Base):
    """REIT disclosures, fund launches, IPOs, dividends, acquisitions."""

    __tablename__ = "capital_markets_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    event_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="REIT_disclosure|fund_launch|IPO|rights_issue|acquisition|dividend"
    )
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticker_if_listed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    value_sar: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InfrastructureEvent(Base):
    """Transport, utility, and industrial zone infrastructure events."""

    __tablename__ = "infrastructure_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    project: Mapped[str | None] = mapped_column(Text, nullable=True)
    infra_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="transport|utility|industrial_zone|port|airport"
    )
    phase: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TenantSignal(Base):
    """Named-tenant expansion, lease, new-site, or M&A signals."""

    __tablename__ = "tenant_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    tenant_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="expansion|new_lease|new_site|M_and_A|closure"
    )
    geography: Mapped[str | None] = mapped_column(String(200), nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarketCommentary(Base):
    """Expert/authority commentary that doesn't fit a more specific fact type."""

    __tablename__ = "market_commentary"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    source_authority: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="Knight Frank|CBRE|JLL|bank_research|government_official|developer_exec|etc"
    )
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quote_under_15_words: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
