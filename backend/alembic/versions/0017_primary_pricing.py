"""Primary pricing fact table for Jawnosc cen mieszkan data.

One row per dwelling per as_of_date snapshot. price_history JSONB tracks
all price changes seen across daily ingestion runs.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op

revision: str = "0017"
down_revision: str = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS primary_pricing (
            id              BIGSERIAL PRIMARY KEY,
            dwelling_id     TEXT NOT NULL,
            developer_id    BIGINT NOT NULL REFERENCES jawnosc_developers(id) ON DELETE CASCADE,
            firm_id         BIGINT REFERENCES developer_firms(id),
            investment_name TEXT,
            district        TEXT,
            city            TEXT,
            street          TEXT,
            voivodeship     TEXT,
            m2_price        NUMERIC(10,2),
            total_price     NUMERIC(12,2),
            unit_area       NUMERIC(8,2),
            unit_type       TEXT,
            status          TEXT NOT NULL DEFAULT 'active',
            price_history   JSONB NOT NULL DEFAULT '[]'::jsonb,
            as_of_date      DATE NOT NULL,
            source_url      TEXT,
            source_format   TEXT,
            schema_variant  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (dwelling_id, developer_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_primary_pricing_district
            ON primary_pricing (district)
        WHERE district IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_primary_pricing_developer
            ON primary_pricing (developer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_primary_pricing_firm
            ON primary_pricing (firm_id)
        WHERE firm_id IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_primary_pricing_status
            ON primary_pricing (status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_primary_pricing_as_of_date
            ON primary_pricing (as_of_date DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_primary_pricing_m2_price
            ON primary_pricing (m2_price)
        WHERE m2_price IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS primary_pricing")
