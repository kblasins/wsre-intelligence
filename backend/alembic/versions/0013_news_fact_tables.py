"""News fact tables — structured signal extraction from articles.

Adds 8 typed fact tables populated by the Sonnet extractor:
  supply_events, regulatory_events, macro_signals, demand_signals,
  capital_markets_events, infrastructure_events, tenant_signals,
  market_commentary

Every row carries consistent lineage: article_id, source_citation,
raw_uri, extracted_at, prompt_sha, model_id, confidence, created_at.

Routing: confidence >= 4 → promoted to table; confidence <= 3 → review_queue.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# Lineage columns shared by every fact table
_LINEAGE = [
    sa.Column("source_citation", sa.Text,         nullable=True),
    sa.Column("raw_uri",         sa.Text,         nullable=True),
    sa.Column("extracted_at",    sa.DateTime(timezone=True), nullable=True),
    sa.Column("prompt_sha",      sa.String(12),   nullable=True),
    sa.Column("model_id",        sa.String(64),   nullable=True),
    sa.Column("confidence",      sa.SmallInteger, nullable=True),
    sa.Column("created_at",      sa.DateTime(timezone=True),
              server_default=sa.text("now()"), nullable=False),
]


def upgrade() -> None:
    op.create_table(
        "supply_events",
        sa.Column("id",                      sa.BigInteger, primary_key=True),
        sa.Column("article_id",              sa.BigInteger, nullable=False),
        sa.Column("event_type",              sa.String(50),  nullable=True),
        sa.Column("developer",               sa.Text,        nullable=True),
        sa.Column("project_name",            sa.Text,        nullable=True),
        sa.Column("location_description",    sa.Text,        nullable=True),
        sa.Column("district_guess",          sa.String(200), nullable=True),
        sa.Column("asset_class",             sa.String(50),  nullable=True),
        sa.Column("gfa_sqm",                 sa.Numeric(14, 2), nullable=True),
        sa.Column("land_area_sqm",           sa.Numeric(14, 2), nullable=True),
        sa.Column("value_sar",               sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_completion_date",sa.String(50),  nullable=True),
        sa.Column("anchor_tenants",          sa.dialects.postgresql.JSONB, nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_supply_events_article", "supply_events", ["article_id"])

    op.create_table(
        "regulatory_events",
        sa.Column("id",            sa.BigInteger, primary_key=True),
        sa.Column("article_id",    sa.BigInteger, nullable=False),
        sa.Column("event_type",    sa.String(50),  nullable=True),
        sa.Column("authority",     sa.String(200), nullable=True),
        sa.Column("scope",         sa.String(50),  nullable=True),
        sa.Column("effective_date",sa.String(50),  nullable=True),
        sa.Column("summary",       sa.Text,        nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_regulatory_events_article", "regulatory_events", ["article_id"])

    op.create_table(
        "macro_signals",
        sa.Column("id",          sa.BigInteger, primary_key=True),
        sa.Column("article_id",  sa.BigInteger, nullable=False),
        sa.Column("indicator",   sa.String(100), nullable=True),
        sa.Column("period",      sa.String(50),  nullable=True),
        sa.Column("value",       sa.Numeric(16, 4), nullable=True),
        sa.Column("direction",   sa.String(10),  nullable=True),
        sa.Column("magnitude",   sa.String(100), nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_macro_signals_article", "macro_signals", ["article_id"])
    op.create_index("ix_macro_signals_indicator", "macro_signals", ["indicator"])

    op.create_table(
        "demand_signals",
        sa.Column("id",          sa.BigInteger, primary_key=True),
        sa.Column("article_id",  sa.BigInteger, nullable=False),
        sa.Column("sector",      sa.String(100), nullable=True),
        sa.Column("metric",      sa.String(200), nullable=True),
        sa.Column("period",      sa.String(50),  nullable=True),
        sa.Column("value",       sa.String(200), nullable=True),
        sa.Column("geography",   sa.String(200), nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_demand_signals_article", "demand_signals", ["article_id"])

    op.create_table(
        "capital_markets_events",
        sa.Column("id",              sa.BigInteger, primary_key=True),
        sa.Column("article_id",      sa.BigInteger, nullable=False),
        sa.Column("event_type",      sa.String(50),  nullable=True),
        sa.Column("entity",          sa.Text,        nullable=True),
        sa.Column("ticker_if_listed",sa.String(20),  nullable=True),
        sa.Column("value_sar",       sa.Numeric(18, 2), nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_capital_markets_events_article", "capital_markets_events", ["article_id"])

    op.create_table(
        "infrastructure_events",
        sa.Column("id",              sa.BigInteger, primary_key=True),
        sa.Column("article_id",      sa.BigInteger, nullable=False),
        sa.Column("project",         sa.Text,        nullable=True),
        sa.Column("infra_type",      sa.String(50),  nullable=True),
        sa.Column("phase",           sa.String(100), nullable=True),
        sa.Column("location",        sa.Text,        nullable=True),
        sa.Column("completion_date", sa.String(50),  nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_infrastructure_events_article", "infrastructure_events", ["article_id"])

    op.create_table(
        "tenant_signals",
        sa.Column("id",           sa.BigInteger, primary_key=True),
        sa.Column("article_id",   sa.BigInteger, nullable=False),
        sa.Column("tenant_name",  sa.Text,        nullable=True),
        sa.Column("industry",     sa.String(200), nullable=True),
        sa.Column("event_type",   sa.String(50),  nullable=True),
        sa.Column("geography",    sa.String(200), nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_tenant_signals_article", "tenant_signals", ["article_id"])

    op.create_table(
        "market_commentary",
        sa.Column("id",                   sa.BigInteger, primary_key=True),
        sa.Column("article_id",           sa.BigInteger, nullable=False),
        sa.Column("source_authority",     sa.String(200), nullable=True),
        sa.Column("topic",                sa.String(200), nullable=True),
        sa.Column("quote_under_15_words", sa.Text,        nullable=True),
        *_LINEAGE,
    )
    op.create_index("ix_market_commentary_article", "market_commentary", ["article_id"])


def downgrade() -> None:
    for tbl in [
        "market_commentary", "tenant_signals", "infrastructure_events",
        "capital_markets_events", "demand_signals", "macro_signals",
        "regulatory_events", "supply_events",
    ]:
        op.drop_table(tbl)
