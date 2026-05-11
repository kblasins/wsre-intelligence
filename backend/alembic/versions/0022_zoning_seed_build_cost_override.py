"""Add build_cost_override_pln_m2_pum to plot_zoning_seed.

Allows per-plot build cost override for mixed-use / non-standard function
codes where the default residential cost (5,500 PLN/m²) underestimates
actual construction cost (e.g. U(MW) high-rise at 7,500 PLN/m²).

NULL means "use function_code default lookup".

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op

revision: str = "0022"
down_revision: str = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE plot_zoning_seed
        ADD COLUMN IF NOT EXISTS build_cost_override_pln_m2_pum NUMERIC
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE plot_zoning_seed
        DROP COLUMN IF EXISTS build_cost_override_pln_m2_pum
    """)
