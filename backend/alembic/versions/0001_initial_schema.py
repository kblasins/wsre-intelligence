"""Initial schema — all tables, indexes, extensions, and fact_resolved view.

Revision ID: 0001
Revises:
Create Date: 2026-04-16

Written as individual op.execute() calls (one statement each) to satisfy
asyncpg's prepared-statement limitation (no multi-statement strings) AND
avoid SQLAlchemy's automatic ENUM type creation hooks.

Prerequisite (run as superuser before migrating):
    psql -U <superuser> wshub -c "
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE EXTENSION IF NOT EXISTS btree_gin;
        CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    "
"""
from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE property_type_enum AS ENUM (
                'warehouse','industrial_land','factory','logistics',
                'office','retail','mixed','residential','other'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_type_enum AS ENUM ('sale','lease','mortgage');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    # ── district_aliases ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS district_aliases (
            id          SERIAL PRIMARY KEY,
            canonical_id INTEGER NOT NULL,
            alias        VARCHAR(300) NOT NULL,
            alias_lang   VARCHAR(10) NOT NULL,
            source       VARCHAR(100),
            name_ar      VARCHAR(300),
            name_en      VARCHAR(300),
            city         VARCHAR(100) NOT NULL DEFAULT 'Riyadh',
            CONSTRAINT uq_district_alias_source UNIQUE (alias, source)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_district_alias_canonical
            ON district_aliases (canonical_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_district_alias_lookup
            ON district_aliases (alias)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_district_alias_trgm
            ON district_aliases USING GIN (alias gin_trgm_ops)
    """)

    # ── transactions ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                 BIGSERIAL PRIMARY KEY,
            transaction_date   DATE NOT NULL,
            district           VARCHAR(200) NOT NULL,
            district_id        INTEGER,
            city               VARCHAR(100) NOT NULL DEFAULT 'Riyadh',
            region             VARCHAR(100) NOT NULL DEFAULT 'Riyadh Region',
            property_type      property_type_enum NOT NULL,
            transaction_type   transaction_type_enum NOT NULL DEFAULT 'sale',
            area_sqm           NUMERIC(12,2),
            price_sar          NUMERIC(14,2) NOT NULL,
            price_per_sqm      NUMERIC(12,2)
                               GENERATED ALWAYS AS
                               (CASE WHEN area_sqm > 0 THEN ROUND(price_sar / area_sqm, 2) END)
                               STORED,
            raw_json           JSONB NOT NULL DEFAULT '{}',
            source_id          VARCHAR(500),
            raw_uri            TEXT,
            extracted_at       TIMESTAMPTZ,
            extractor_version  VARCHAR(32),
            prompt_sha         VARCHAR(12),
            model_id           VARCHAR(64),
            confidence         SMALLINT,
            source_priority    SMALLINT NOT NULL DEFAULT 1,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_transactions_source_id  UNIQUE (source_id),
            CONSTRAINT ck_tx_positive_area        CHECK (area_sqm > 0),
            CONSTRAINT ck_tx_positive_price       CHECK (price_sar > 0),
            CONSTRAINT ck_tx_confidence           CHECK (confidence BETWEEN 1 AND 5),
            CONSTRAINT ck_tx_source_priority      CHECK (source_priority BETWEEN 1 AND 4)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tx_district_date
            ON transactions (district, transaction_date DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tx_ptype_district_date
            ON transactions (property_type, district, transaction_date DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tx_date_brin
            ON transactions USING BRIN (transaction_date)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tx_raw_gin
            ON transactions USING GIN (raw_json jsonb_path_ops)
    """)

    # ── reit_snapshots ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS reit_snapshots (
            id                        BIGSERIAL PRIMARY KEY,
            ticker                    VARCHAR(20) NOT NULL,
            snapshot_date             DATE NOT NULL,
            price_sar                 NUMERIC(12,4),
            nav_per_unit_sar          NUMERIC(14,4),
            nav_discount_pct          NUMERIC(7,4),
            ffo_per_unit_sar          NUMERIC(12,4),
            distribution_per_unit_sar NUMERIC(12,4),
            implied_cap_rate_pct      NUMERIC(7,4),
            occupancy_pct             NUMERIC(5,2),
            total_assets_sar          NUMERIC(18,2),
            raw_json                  JSONB NOT NULL DEFAULT '{}',
            source_id                 VARCHAR(200),
            raw_uri                   TEXT,
            extracted_at              TIMESTAMPTZ,
            model_id                  VARCHAR(64),
            prompt_sha                VARCHAR(12),
            created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_reit_ticker_date UNIQUE (ticker, snapshot_date)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_reit_snap_ticker_date
            ON reit_snapshots (ticker, snapshot_date DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_reit_snap_date_brin
            ON reit_snapshots USING BRIN (snapshot_date)
    """)

    # ── listings ───────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id                BIGSERIAL PRIMARY KEY,
            portal            VARCHAR(50) NOT NULL,
            external_id       VARCHAR(200) NOT NULL,
            listing_type      VARCHAR(10) NOT NULL,
            property_type     property_type_enum NOT NULL,
            district          VARCHAR(200),
            district_id       INTEGER,
            city              VARCHAR(100) NOT NULL DEFAULT 'Riyadh',
            area_sqm          NUMERIC(12,2),
            price_sar         NUMERIC(14,2),
            rent_sar_annual   NUMERIC(14,2),
            listed_at         TIMESTAMPTZ,
            is_active         BOOLEAN NOT NULL DEFAULT true,
            url               TEXT,
            raw_json          JSONB NOT NULL DEFAULT '{}',
            raw_uri           TEXT,
            extracted_at      TIMESTAMPTZ,
            extractor_version VARCHAR(32),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_listing_portal_external_id UNIQUE (portal, external_id),
            CONSTRAINT ck_listing_type CHECK (listing_type IN ('sale','lease'))
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_listing_portal_district_date
            ON listings (portal, district, listed_at DESC)
    """)

    # ── news_articles ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id               BIGSERIAL PRIMARY KEY,
            source           VARCHAR(100) NOT NULL,
            external_id      VARCHAR(500) NOT NULL,
            title_ar         TEXT,
            title_en         TEXT,
            body_ar          TEXT,
            body_en          TEXT,
            url              TEXT,
            published_at     TIMESTAMPTZ,
            relevance_score  NUMERIC(4,3),
            structured_facts JSONB NOT NULL DEFAULT '{}',
            raw_uri          TEXT,
            extracted_at     TIMESTAMPTZ,
            prompt_sha       VARCHAR(12),
            model_id         VARCHAR(64),
            confidence       SMALLINT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_article_source_external_id UNIQUE (source, external_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_article_source_published
            ON news_articles (source, published_at DESC)
    """)

    # ── tenders ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenders (
            id           BIGSERIAL PRIMARY KEY,
            etimad_id    VARCHAR(200) NOT NULL,
            entity_name  VARCHAR(500),
            title_ar     TEXT,
            title_en     TEXT,
            value_sar    NUMERIC(18,2),
            published_at TIMESTAMPTZ,
            deadline_at  TIMESTAMPTZ,
            raw_json     JSONB NOT NULL DEFAULT '{}',
            raw_uri      TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tender_etimad_id UNIQUE (etimad_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tender_entity_published
            ON tenders (entity_name, published_at DESC)
    """)

    # ── raw_ingest_outbox ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_ingest_outbox (
            id               BIGSERIAL PRIMARY KEY,
            source           VARCHAR(100) NOT NULL,
            raw_uri          TEXT NOT NULL,
            content_sha1     VARCHAR(40) NOT NULL,
            content_type     VARCHAR(100) NOT NULL DEFAULT 'text/html',
            structured       SMALLINT NOT NULL DEFAULT 0,
            structured_at    TIMESTAMPTZ,
            extraction_error TEXT,
            retry_count      INTEGER NOT NULL DEFAULT 0,
            fetched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            scraper_meta     JSONB NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outbox_pending
            ON raw_ingest_outbox (structured, fetched_at)
            WHERE structured = 0
    """)

    # ── source_registry ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS source_registry (
            id                   SERIAL PRIMARY KEY,
            source_key           VARCHAR(100) NOT NULL UNIQUE,
            display_name         VARCHAR(200) NOT NULL,
            source_type          VARCHAR(50) NOT NULL,
            base_url             TEXT,
            is_enabled           BOOLEAN NOT NULL DEFAULT true,
            priority             SMALLINT NOT NULL DEFAULT 4,
            last_attempt_at      TIMESTAMPTZ,
            last_success_at      TIMESTAMPTZ,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            notes                TEXT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── llm_calls ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id                 BIGSERIAL PRIMARY KEY,
            model_id           VARCHAR(64) NOT NULL,
            prompt_sha         VARCHAR(64) NOT NULL,
            task_type          VARCHAR(50) NOT NULL,
            input_tokens       BIGINT NOT NULL DEFAULT 0,
            output_tokens      BIGINT NOT NULL DEFAULT 0,
            cache_write_tokens BIGINT NOT NULL DEFAULT 0,
            cache_read_tokens  BIGINT NOT NULL DEFAULT 0,
            cost_usd           NUMERIC(10,6) NOT NULL DEFAULT 0,
            is_batch           BOOLEAN NOT NULL DEFAULT false,
            batch_id           VARCHAR(200),
            outbox_id          BIGINT,
            success            BOOLEAN NOT NULL DEFAULT true,
            error_message      TEXT,
            called_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_llm_calls_date_brin
            ON llm_calls USING BRIN (called_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_llm_calls_model_task
            ON llm_calls (model_id, task_type)
    """)

    # ── review_queue ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS review_queue (
            id               BIGSERIAL PRIMARY KEY,
            source_table     VARCHAR(100) NOT NULL,
            source_row_id    BIGINT NOT NULL,
            raw_uri          TEXT,
            model_id         VARCHAR(64),
            prompt_sha       VARCHAR(12),
            confidence       SMALLINT,
            llm_output       JSONB NOT NULL DEFAULT '{}',
            uncertain_fields JSONB NOT NULL DEFAULT '[]',
            reviewed_by      VARCHAR(200),
            reviewed_at      TIMESTAMPTZ,
            resolution       VARCHAR(20),
            corrected_output JSONB,
            is_golden        BOOLEAN NOT NULL DEFAULT false,
            expected_output  JSONB,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_review_pending
            ON review_queue (reviewed_at, is_golden)
            WHERE reviewed_at IS NULL
    """)

    # ── users (fastapi-users) ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email           VARCHAR(320) NOT NULL UNIQUE,
            hashed_password VARCHAR(1024) NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT true,
            is_superuser    BOOLEAN NOT NULL DEFAULT false,
            is_verified     BOOLEAN NOT NULL DEFAULT false
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)
    """)

    # ── fact_resolved materialized view ────────────────────────────────────
    # Picks the best-priority source for each (district, property_type, period).
    # Refreshed weekly before the brief runs (Sunday 05:00 UTC).
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS fact_resolved AS
        SELECT
            transaction_date                                                    AS period,
            district,
            property_type::text,
            AVG(price_per_sqm) FILTER (WHERE price_per_sqm IS NOT NULL)         AS avg_price_per_sqm,
            COUNT(*)                                                             AS n_transactions,
            MIN(source_priority)                                                 AS best_priority,
            MAX(created_at)                                                      AS latest_at
        FROM transactions
        GROUP BY transaction_date, district, property_type
        WITH NO DATA
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_fact_resolved
            ON fact_resolved (period, district, property_type)
    """)

    # ── Source registry seed ───────────────────────────────────────────────
    op.execute("""
        INSERT INTO source_registry
            (source_key, display_name, source_type, base_url, priority, notes)
        VALUES
            ('rega',           'REGA / SREM Indicators',       'scraper',
             'https://srem.moj.gov.sa', 1,
             'URL is srem.moj.gov.sa (Ministry of Justice) — NOT srem.rega.gov.sa. Requires DevTools XHR capture.'),
            ('tadawul',        'Tadawul REIT Prices',          'api',
             'https://saudiexchange.sa', 1,
             'yfinance .SR suffix, 15-min delayed. Priority: 4331, 4339, 4340.'),
            ('knight_frank',   'Knight Frank Reports',         'pdf',
             'https://knightfrank.com', 2, NULL),
            ('cbre',           'CBRE MarketView Riyadh',       'pdf',
             'https://cbre.com', 2, NULL),
            ('jll',            'JLL KSA Market Reports',       'pdf',
             'https://jll.com', 2, NULL),
            ('argaam_en',      'Argaam (English)',              'scraper',
             'https://argaam.com', 3, NULL),
            ('argaam_ar',      'Argaam (Arabic)',               'scraper',
             'https://argaam.com', 3, NULL),
            ('modon',          'MODON Press Releases',         'scraper',
             'https://modon.gov.sa', 3,
             'SharePoint-based, no RSS. News cadence: weeks-to-months.'),
            ('etimad',         'Etimad Tenders',               'api',
             'https://apiportal.etimad.sa', 3,
             'Official API — requires Business account registration at apiportal.etimad.sa.'),
            ('aqar',           'Aqar.fm Warehouse Listings',   'scraper',
             'https://sa.aqar.fm', 4,
             'CF WAF. Pattern: /en/warehouse-for-rent/{city}/{district}.'),
            ('bayut',          'Bayut.sa Listings',            'apify',
             'https://bayut.sa', 4,
             'Use Apify actor dhrumil/bayut-scraper to shift ToS risk to vendor.'),
            ('propertyfinder', 'PropertyFinder SA Listings',   'apify',
             'https://propertyfinder.sa', 4, NULL),
            ('wasalt',         'Wasalt.sa Listings',           'scraper',
             'https://wasalt.sa', 4,
             'React + WebSockets. Playwright + XHR intercept. DevTools capture needed.')
        ON CONFLICT (source_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS fact_resolved")
    op.execute("DROP TABLE IF EXISTS review_queue CASCADE")
    op.execute("DROP TABLE IF EXISTS llm_calls CASCADE")
    op.execute("DROP TABLE IF EXISTS source_registry CASCADE")
    op.execute("DROP TABLE IF EXISTS raw_ingest_outbox CASCADE")
    op.execute("DROP TABLE IF EXISTS tenders CASCADE")
    op.execute("DROP TABLE IF EXISTS news_articles CASCADE")
    op.execute("DROP TABLE IF EXISTS listings CASCADE")
    op.execute("DROP TABLE IF EXISTS reit_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS district_aliases CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TYPE IF EXISTS property_type_enum")
    op.execute("DROP TYPE IF EXISTS transaction_type_enum")
