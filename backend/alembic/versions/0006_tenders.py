"""Add tenders table (Etimad government procurement).

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("etimad_id", sa.String(length=100), nullable=False),
        sa.Column("entity_name", sa.String(length=500), nullable=True),
        sa.Column("title_ar", sa.Text(), nullable=True),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column("value_sar", sa.Numeric(18, 2), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_uri", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("etimad_id", name="uq_tender_etimad_id"),
    )
    op.create_index("ix_tender_published_at", "tenders", ["published_at"])
    op.create_index("ix_tender_deadline_at", "tenders", ["deadline_at"])
    op.create_index("ix_tender_entity_name", "tenders", ["entity_name"])


def downgrade() -> None:
    op.drop_index("ix_tender_entity_name", table_name="tenders")
    op.drop_index("ix_tender_deadline_at", table_name="tenders")
    op.drop_index("ix_tender_published_at", table_name="tenders")
    op.drop_table("tenders")
