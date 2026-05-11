"""Developer firms parent table + FK on jawnosc_developers.

Adds:
  developer_firms          — enterprise-level developer roll-up
  jawnosc_developers.firm_id — FK to developer_firms
  jawnosc_developers.last_seen_date — feed-internal freshness date
  jawnosc_developers.feed_freshness — 'active' | 'recently_active' | 'stale'

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op

revision: str = "0016"
down_revision: str = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS developer_firms (
            id                  BIGSERIAL PRIMARY KEY,
            firm_name           TEXT NOT NULL,
            firm_name_normalized TEXT NOT NULL,
            firm_initials       TEXT,
            parent_company      TEXT,
            legal_form          TEXT,
            is_warsaw_active    BOOLEAN NOT NULL DEFAULT FALSE,
            investments_count   INT NOT NULL DEFAULT 0,
            units_active        INT NOT NULL DEFAULT 0,
            median_pln_m2       NUMERIC(10,2),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (firm_name_normalized)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_firms_warsaw
            ON developer_firms (is_warsaw_active)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_firms_name_normalized
            ON developer_firms (firm_name_normalized)
    """)

    # Add columns to jawnosc_developers
    op.execute("""
        ALTER TABLE jawnosc_developers
            ADD COLUMN IF NOT EXISTS firm_id BIGINT REFERENCES developer_firms(id),
            ADD COLUMN IF NOT EXISTS last_seen_date DATE,
            ADD COLUMN IF NOT EXISTS feed_freshness TEXT DEFAULT 'unknown'
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_jawnosc_developers_firm_id
            ON jawnosc_developers (firm_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE jawnosc_developers DROP COLUMN IF EXISTS feed_freshness")
    op.execute("ALTER TABLE jawnosc_developers DROP COLUMN IF EXISTS last_seen_date")
    op.execute("ALTER TABLE jawnosc_developers DROP COLUMN IF EXISTS firm_id")
    op.execute("DROP TABLE IF EXISTS developer_firms")
