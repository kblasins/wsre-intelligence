"""Macro indicators table — manually maintained, seeded with current reference values.

Adds macro_indicators (one row per key). Source='manual', fetched_at=NOW() so
the data is explicitly not pretending to be live-scraped.

Automated scraping deferred to a later phase.

Valid keys: sama_repo_rate, sar_usd, brent, saudi_10y_yield, cpi_yoy,
            riyadh_population
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_SEED = [
    # (indicator_key, value, period, source, source_url)
    (
        "sama_repo_rate",
        6.00,
        "2026-Q1",
        "manual",
        "https://www.sama.gov.sa/en-US/MonetaryPolicies/Pages/MonetaryPolicies.aspx",
    ),
    (
        "sar_usd",
        3.7500,
        "2026-Q1",
        "manual",
        "https://www.sama.gov.sa/en-US/EconomicReports/Pages/ExchangeRates.aspx",
    ),
    (
        "brent",
        82.0,
        "2026-04",
        "manual",
        None,
    ),
    (
        "saudi_10y_yield",
        5.60,
        "2026-03",
        "manual",
        None,
    ),
    (
        "cpi_yoy",
        1.70,
        "2026-02",
        "manual",
        "https://www.stats.gov.sa/en/news",
    ),
    (
        "riyadh_population",
        7_700_000,
        "2025",
        "manual",
        "https://www.stats.gov.sa/en/5305",
    ),
]


def upgrade() -> None:
    op.create_table(
        "macro_indicators",
        sa.Column("indicator_key", sa.String(100), primary_key=True),
        sa.Column("value",      sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("period",     sa.String(20),  nullable=False),
        sa.Column("source",     sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text,        nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.execute(
        sa.text("""
            INSERT INTO macro_indicators
                (indicator_key, value, period, source, source_url, fetched_at)
            VALUES
                ('sama_repo_rate',    6.00,       '2026-Q1', 'manual', 'https://www.sama.gov.sa/en-US/MonetaryPolicies/Pages/MonetaryPolicies.aspx', NOW()),
                ('sar_usd',          3.7500,      '2026-Q1', 'manual', 'https://www.sama.gov.sa/en-US/EconomicReports/Pages/ExchangeRates.aspx', NOW()),
                ('brent',            82.0,        '2026-04', 'manual', NULL, NOW()),
                ('saudi_10y_yield',   5.60,       '2026-03', 'manual', NULL, NOW()),
                ('cpi_yoy',           1.70,       '2026-02', 'manual', 'https://www.stats.gov.sa/en/news', NOW()),
                ('riyadh_population', 7700000,    '2025',    'manual', 'https://www.stats.gov.sa/en/5305', NOW())
        """)
    )


def downgrade() -> None:
    op.drop_table("macro_indicators")
