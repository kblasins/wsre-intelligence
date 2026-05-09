"""Phase 3.5b — district_velocity materialized view.

Aggregates transaction data by district × property_type × month to power
the velocity heatmap layer on the Workbench map.

Computes:
  - transaction count
  - total value SAR
  - avg price per sqm SAR
  - 3-month rolling avg price per sqm (for momentum)

Refreshed weekly (Sunday 03:00 UTC) alongside the POI refresh.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-18
"""

from __future__ import annotations

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── district_velocity materialized view ────────────────────────────────
    # Joins transactions → district_aliases (canonical_id lookup) to attach
    # the canonical district name to each transaction, then aggregates.
    #
    # Falls back to transactions.district text column when spatial join is
    # not available (transactions without location still count via name match).
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS district_velocity AS
        WITH monthly AS (
            SELECT
                COALESCE(da.canonical_id::text, t.district)   AS district_key,
                COALESCE(da.name_en, t.district)              AS district_name,
                t.property_type,
                DATE_TRUNC('month', t.transaction_date)       AS month,
                COUNT(*)                                      AS tx_count,
                SUM(t.price_sar)                              AS total_sar,
                AVG(t.price_sar / NULLIF(t.area_sqm, 0))      AS avg_price_per_sqm
            FROM transactions t
            LEFT JOIN district_aliases da
                ON LOWER(da.alias) = LOWER(t.district)
            WHERE t.transaction_date IS NOT NULL
              AND t.district IS NOT NULL
            GROUP BY 1, 2, 3, 4
        ),
        with_rolling AS (
            SELECT
                district_key,
                district_name,
                property_type,
                month,
                tx_count,
                total_sar,
                avg_price_per_sqm,
                AVG(avg_price_per_sqm) OVER (
                    PARTITION BY district_key, property_type
                    ORDER BY month
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) AS rolling_3m_avg_per_sqm
            FROM monthly
        )
        SELECT
            ROW_NUMBER() OVER ()              AS id,
            district_key,
            district_name,
            property_type,
            month,
            tx_count,
            ROUND(total_sar, 2)               AS total_sar,
            ROUND(avg_price_per_sqm::numeric, 2)      AS avg_price_per_sqm,
            ROUND(rolling_3m_avg_per_sqm::numeric, 2) AS rolling_3m_avg_per_sqm,
            -- Momentum: % change vs 3-month rolling average
            CASE
                WHEN rolling_3m_avg_per_sqm > 0 THEN
                    ROUND(
                        ((avg_price_per_sqm - rolling_3m_avg_per_sqm)
                         / rolling_3m_avg_per_sqm * 100)::numeric,
                        2
                    )
                ELSE NULL
            END AS momentum_pct
        FROM with_rolling
        ORDER BY month DESC, tx_count DESC
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_district_velocity_pk
            ON district_velocity (id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_district_velocity_month
            ON district_velocity (month)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_district_velocity_district_type
            ON district_velocity (district_key, property_type)
    """)

    # ── district_velocity_summary convenience view ─────────────────────────
    # Latest 90-day window aggregated per district — used by the heat-map
    # color scale endpoint.
    op.execute("""
        CREATE OR REPLACE VIEW district_velocity_summary AS
        SELECT
            district_key,
            district_name,
            property_type,
            SUM(tx_count)                              AS tx_count_90d,
            ROUND(AVG(avg_price_per_sqm)::numeric, 2)  AS avg_price_per_sqm_90d,
            ROUND(AVG(momentum_pct)::numeric, 2)        AS avg_momentum_pct,
            MAX(month)                                 AS latest_month
        FROM district_velocity
        WHERE month >= DATE_TRUNC('month', NOW() - INTERVAL '90 days')
        GROUP BY district_key, district_name, property_type
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS district_velocity_summary")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS district_velocity CASCADE")
