"""Add rent_index table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-16
"""

from __future__ import annotations

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS rent_index (
            id                   BIGSERIAL PRIMARY KEY,
            district             VARCHAR(200),
            city                 VARCHAR(100) NOT NULL DEFAULT 'Riyadh',
            property_type        property_type_enum NOT NULL,
            period               VARCHAR(20) NOT NULL,
            rent_sar_sqm_annual  NUMERIC(12,2),
            yoy_change_pct       NUMERIC(7,4),
            vacancy_pct          NUMERIC(5,2),
            source               VARCHAR(100) NOT NULL,
            source_priority      SMALLINT NOT NULL DEFAULT 2,
            raw_uri              TEXT,
            extracted_at         TIMESTAMPTZ,
            prompt_sha           VARCHAR(12),
            model_id             VARCHAR(64),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_rent_index_district_type_period_source
                UNIQUE (district, property_type, period, source)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rent_idx_district_period
            ON rent_index (district, period DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rent_idx_ptype_period
            ON rent_index (property_type, period DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rent_index")
