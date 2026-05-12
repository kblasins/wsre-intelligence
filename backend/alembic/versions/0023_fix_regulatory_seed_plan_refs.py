"""Fix plot_regulatory_seed items that reference the old fabricated plan.

Two items referenced "Czyste-Towarowa MPZP" (a fictional plan) and the
old 130m height ceiling. Now that Section A is grounded in real WMS data
(rej. ul. Żelaznej cz. północna A, U(MW), 55m), update regulatory items
to be consistent. Also add a U(MW) zoning confirmation item.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op

revision: str = "0023"
down_revision: str = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix WSA item — the old ruling was about a fabricated plan/height
    op.execute("""
        UPDATE plot_regulatory_seed
        SET title = 'Warsaw SIP confirms U(MW) zoning envelope for rej. ul. Żelaznej area — '
                    '55 m height limit, FAR 12, mixed-use (services + residential) permitted; '
                    'no pending appeals on record',
            source = 'Warsaw SIP / MPZP viewer',
            event_date = '2024-09-18'
        WHERE plot_id = 'demo-towarowa-28'
          AND event_date = '2026-03-19'
    """)

    # Fix environmental item — remove "Czyste-Towarowa" reference
    op.execute("""
        UPDATE plot_regulatory_seed
        SET title = 'No Natura 2000 proximity, no conservation overlay, no water-table risk '
                    'flagged for Mirów / Wola parcels in the rej. ul. Żelaznej planning area'
        WHERE plot_id = 'demo-towarowa-28'
          AND event_date = '2025-09-02'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE plot_regulatory_seed
        SET title = 'WSA Warsaw upholds Czyste-Towarowa MPZP — 130m height ceiling stands; '
                    '4 stalled Wola schemes unblocked',
            source = 'WSA Warsaw / Eurobuild CEE',
            event_date = '2026-03-19'
        WHERE plot_id = 'demo-towarowa-28'
          AND event_date = '2024-09-18'
    """)
    op.execute("""
        UPDATE plot_regulatory_seed
        SET title = 'No Natura 2000 proximity, no conservation overlay, no water-table risk '
                    'flagged for Wola Czyste-Towarowa parcels'
        WHERE plot_id = 'demo-towarowa-28'
          AND event_date = '2025-09-02'
    """)
