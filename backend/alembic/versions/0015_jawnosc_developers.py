"""Jawnosc cen mieszkan — developer registry table.

Stores the dane.gov.pl dataset metadata for every developer who publishes
Jawnosc pricing data under Dz.U. 2023 poz. 1114 (art. 19b).

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op

revision: str = "0015"
down_revision: str = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS jawnosc_developers (
            id                      BIGSERIAL PRIMARY KEY,
            developer_name          TEXT NOT NULL,
            developer_id            TEXT NOT NULL,
            institution_id          TEXT,
            dataset_url             TEXT NOT NULL,
            feed_url                TEXT,
            schema_version          TEXT,
            last_sync               TIMESTAMPTZ,
            sync_status             TEXT NOT NULL DEFAULT 'pending',
            coverage_districts      TEXT[],
            active_investments_count INT DEFAULT 0,
            active_units_count      INT DEFAULT 0,
            city_hq                 TEXT,
            dataset_modified        TIMESTAMPTZ,
            data_format             TEXT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (developer_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_jawnosc_developers_sync_status
            ON jawnosc_developers (sync_status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_jawnosc_developers_coverage_districts
            ON jawnosc_developers USING GIN (coverage_districts)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_jawnosc_developers_dataset_modified
            ON jawnosc_developers (dataset_modified DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS jawnosc_developers")
