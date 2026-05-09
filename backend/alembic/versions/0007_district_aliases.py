"""Add district_aliases table (canonical district name registry).

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "district_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(300), nullable=False),
        sa.Column("alias_lang", sa.String(10), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("name_ar", sa.String(300), nullable=True),
        sa.Column("name_en", sa.String(300), nullable=True),
        sa.Column("city", sa.String(100), nullable=False, server_default="Riyadh"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias", "source", name="uq_district_alias_source"),
    )
    op.create_index("ix_district_alias_canonical", "district_aliases", ["canonical_id"])
    op.create_index("ix_district_alias_lookup", "district_aliases", ["alias"])


def downgrade() -> None:
    op.drop_index("ix_district_alias_lookup", table_name="district_aliases")
    op.drop_index("ix_district_alias_canonical", table_name="district_aliases")
    op.drop_table("district_aliases")
