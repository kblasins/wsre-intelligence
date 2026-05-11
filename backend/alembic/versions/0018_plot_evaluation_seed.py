"""Plot evaluation seed tables for hand-curated demo data.

Five tables supplement live Jawność data for the Plot Evaluation right-rail panel.
Populated initially for plot_id = 'demo-towarowa-28' (ul. Towarowa 28, Wola).

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-10
"""
from __future__ import annotations

from alembic import op

revision: str = "0018"
down_revision: str = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plot_zoning_seed (
            plot_id                  TEXT PRIMARY KEY,
            mpzp_name                TEXT,
            mpzp_enacted_date        DATE,
            mpzp_resolution_id       TEXT,
            function_code            TEXT,
            max_far                  NUMERIC,
            max_height_m             NUMERIC,
            max_site_coverage_pct    NUMERIC,
            min_greenery_pct         NUMERIC,
            min_parking_ratio        NUMERIC,
            front_setback_m          NUMERIC,
            notes                    TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plot_land_comps_seed (
            id               BIGSERIAL PRIMARY KEY,
            plot_id          TEXT NOT NULL,
            transaction_date DATE,
            distance_m       INT,
            area_m2          NUMERIC,
            pln_per_m2       NUMERIC,
            market_type      TEXT,
            source           TEXT,
            is_demo_seed     BOOLEAN DEFAULT TRUE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plot_demographics_seed (
            plot_id                      TEXT PRIMARY KEY,
            district                     TEXT,
            population_current           INT,
            population_5y_trajectory_pct NUMERIC,
            age_25_44_share_pct          NUMERIC,
            age_25_44_vs_warsaw_avg_pct  NUMERIC,
            avg_monthly_earnings_pln     INT,
            earnings_3y_trajectory_pct   NUMERIC,
            dwellings_per_1000           INT,
            supply_status                TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plot_infrastructure_seed (
            plot_id               TEXT PRIMARY KEY,
            nearest_metro         TEXT,
            metro_distance_min    INT,
            nearest_tram          TEXT,
            tram_distance_min     INT,
            planned_transport     TEXT,
            schools_1km_count     INT,
            healthcare_2km_count  INT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plot_regulatory_seed (
            id         BIGSERIAL PRIMARY KEY,
            plot_id    TEXT NOT NULL,
            event_date DATE,
            title      TEXT,
            source     TEXT,
            link_url   TEXT
        )
    """)

    # ── Seed data for demo-towarowa-28 ──────────────────────────────────────

    op.execute("""
        INSERT INTO plot_zoning_seed (
            plot_id, mpzp_name, mpzp_enacted_date, mpzp_resolution_id,
            function_code, max_far, max_height_m, max_site_coverage_pct,
            min_greenery_pct, min_parking_ratio, front_setback_m, notes
        ) VALUES (
            'demo-towarowa-28',
            'Plan miejscowy obszaru „Czyste — Towarowa"',
            '2026-03-12',
            'Uchwała Rady m. st. Warszawy LXEX/2336/2026',
            'MW — multi-family residential',
            5.0,
            130.0,
            70.0,
            25.0,
            1.2,
            5.0,
            '"Plan miejscowego obszaru „Czyste — Towarowa" reaffirms 130 m max height for parcels fronting ul. Towarowa — Uchwała Rady m. st. Warszawy LXEX/2336/2026, 12 Mar 2026'
        )
        ON CONFLICT (plot_id) DO NOTHING
    """)

    op.execute("""
        INSERT INTO plot_land_comps_seed
            (plot_id, transaction_date, distance_m, area_m2, pln_per_m2, market_type, source)
        VALUES
            ('demo-towarowa-28', '2025-11-14', 320,  2840, 4250, 'primary',   'RCN/GUS BDL'),
            ('demo-towarowa-28', '2025-08-02', 510,  1560, 3980, 'primary',   'RCN/GUS BDL'),
            ('demo-towarowa-28', '2025-06-19', 780,  3210, 4120, 'secondary', 'RCN/GUS BDL'),
            ('demo-towarowa-28', '2025-03-27', 240,  890,  4380, 'primary',   'RCN/GUS BDL'),
            ('demo-towarowa-28', '2024-12-05', 640,  1980, 3750, 'secondary', 'RCN/GUS BDL'),
            ('demo-towarowa-28', '2024-09-11', 420,  4120, 4050, 'primary',   'RCN/GUS BDL'),
            ('demo-towarowa-28', '2024-07-22', 890,  2300, 3860, 'secondary', 'RCN/GUS BDL'),
            ('demo-towarowa-28', '2024-04-08', 360,  1670, 3690, 'primary',   'RCN/GUS BDL')
    """)

    op.execute("""
        INSERT INTO plot_demographics_seed (
            plot_id, district, population_current, population_5y_trajectory_pct,
            age_25_44_share_pct, age_25_44_vs_warsaw_avg_pct,
            avg_monthly_earnings_pln, earnings_3y_trajectory_pct,
            dwellings_per_1000, supply_status
        ) VALUES (
            'demo-towarowa-28',
            'wola',
            138200,
            4.2,
            34.1,
            8.3,
            8640,
            18.7,
            412,
            'undersupplied'
        )
        ON CONFLICT (plot_id) DO NOTHING
    """)

    op.execute("""
        INSERT INTO plot_infrastructure_seed (
            plot_id, nearest_metro, metro_distance_min, nearest_tram,
            tram_distance_min, planned_transport, schools_1km_count, healthcare_2km_count
        ) VALUES (
            'demo-towarowa-28',
            'Rondo Daszyńskiego (M2)',
            8,
            'Towarowa / Ogrodowa (lines 10, 24, 33)',
            3,
            'Metro C (planned 2031) — Czyste station 400 m; tram line 28 extension to Wolska 2027',
            4,
            6
        )
        ON CONFLICT (plot_id) DO NOTHING
    """)

    op.execute("""
        INSERT INTO plot_regulatory_seed (plot_id, event_date, title, source, link_url)
        VALUES
            ('demo-towarowa-28', '2026-03-12',
             'MPZP „Czyste — Towarowa" enacted — MW function confirmed, 130 m height',
             'Dziennik Urzędowy m.st. Warszawy',
             'https://bip.warszawa.pl/mpzp/czyste-towarowa-2026'),
            ('demo-towarowa-28', '2025-11-04',
             'Environmental screening opinion issued — no EIA required',
             'Regionalny Dyrektor Ochrony Środowiska',
             NULL),
            ('demo-towarowa-28', '2025-07-18',
             'Heritage register check — plot not within conservation zone',
             'Mazowiecki Konserwator Zabytków',
             NULL),
            ('demo-towarowa-28', '2025-03-01',
             'Wola district spatial study (SUiKZP) update — Towarowa corridor designated strategic mixed-use',
             'Biuro Architektury i Planowania Przestrzennego',
             'https://bap.warszawa.pl/suikzp-2025')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plot_regulatory_seed")
    op.execute("DROP TABLE IF EXISTS plot_infrastructure_seed")
    op.execute("DROP TABLE IF EXISTS plot_demographics_seed")
    op.execute("DROP TABLE IF EXISTS plot_land_comps_seed")
    op.execute("DROP TABLE IF EXISTS plot_zoning_seed")
