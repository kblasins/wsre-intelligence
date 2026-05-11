"""Update demo-towarowa-28 plot_zoning_seed to match WMS reality.

Corrects plan name, function code, max_height_m, max_far, and notes
to match data returned by Warsaw WMS (MPZP_PRZEZNACZENIE_TERENU layer):
  - Plan: rej. ul. Żelaznej cz. północna A
  - Zone: U(MW) — usługi z zabudową wielorodzinną
  - Max height: 55 m  (was 130 m)
  - Max FAR: 12       (was 5.0)

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op

revision: str = "0021"
down_revision: str = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE plot_zoning_seed SET
            mpzp_name    = 'rej. ul. Żelaznej cz. północna A',
            function_code = 'U(MW) — usługi z zabudową wielorodzinną (mixed-use: services + residential)',
            max_far       = 12,
            max_height_m  = 55,
            notes         = 'Plan zezwala na zabudowę usługową z towarzyszącą zabudową wielorodzinną. '
                            'Wysokość zabudowy do 55 m. Intensywność zabudowy do 12. '
                            'Źródło: WMS m.st. Warszawy.'
        WHERE plot_id = 'demo-towarowa-28'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE plot_zoning_seed SET
            mpzp_name     = 'Plan miejscowy obszaru „Czyste — Towarowa"',
            function_code = 'MW — multi-family residential',
            max_far       = 5.0,
            max_height_m  = 130.0,
            notes         = '"Plan miejscowego obszaru „Czyste — Towarowa" reaffirms 130 m max height '
                            'for parcels fronting ul. Towarowa — '
                            'Uchwała Rady m. st. Warszawy LXEX/2336/2026, 12 Mar 2026'
        WHERE plot_id = 'demo-towarowa-28'
    """)
