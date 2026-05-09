"""Add weekly_briefs table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-17
"""

from __future__ import annotations

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS weekly_briefs (
            id BIGSERIAL PRIMARY KEY,
            week_ending DATE NOT NULL UNIQUE,
            brief_text TEXT NOT NULL,
            brief_json JSONB NOT NULL DEFAULT '{}',
            model_id VARCHAR(64) NOT NULL,
            prompt_sha VARCHAR(12) NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0.0,
            pdf_uri TEXT,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_brief_week_ending ON weekly_briefs (week_ending DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS weekly_briefs")
