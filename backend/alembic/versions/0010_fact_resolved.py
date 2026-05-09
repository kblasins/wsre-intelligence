"""Create fact_resolved materialized view with source_priority tiebreaker.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-18

Source-priority hierarchy (lower = more authoritative):
  1 = REGA official data, Tadawul
  2 = Knight Frank / CBRE / JLL research reports
  3 = Argaam / news articles
  4 = Aqar / Bayut (asking prices, not transacted)

For each (district, property_type, period) combination the view keeps
the reading from the most authoritative source. When two rows share the
same priority the most recently extracted one wins.

The view is refreshed nightly (Sunday 04:30 UTC) by the scheduler.
CONCURRENTLY refresh requires the supporting UNIQUE INDEX below.
"""

from __future__ import annotations

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop any pre-existing view (may exist from manual/test runs) before creating
    op.execute("DROP MATERIALIZED VIEW IF EXISTS fact_resolved CASCADE")

    op.execute("""
        CREATE MATERIALIZED VIEW fact_resolved AS
        SELECT DISTINCT ON (COALESCE(district, ''), property_type, period)
            id,
            district,
            city,
            property_type,
            period,
            rent_sar_sqm_annual,
            yoy_change_pct,
            vacancy_pct,
            source,
            source_priority,
            raw_uri,
            extracted_at,
            model_id,
            prompt_sha
        FROM rent_index
        ORDER BY
            COALESCE(district, ''),
            property_type,
            period,
            source_priority ASC NULLS LAST,
            extracted_at DESC NULLS LAST
    """)

    # UNIQUE INDEX required for REFRESH MATERIALIZED VIEW CONCURRENTLY
    op.execute("""
        CREATE UNIQUE INDEX ix_fact_resolved_pk
            ON fact_resolved (id)
    """)

    op.execute("""
        CREATE INDEX ix_fact_resolved_district_period
            ON fact_resolved (district, period)
    """)

    op.execute("""
        CREATE INDEX ix_fact_resolved_ptype_period
            ON fact_resolved (property_type, period)
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS fact_resolved CASCADE")
