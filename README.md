# White Star Market Intelligence Hub

Riyadh industrial real estate intelligence platform for White Star Real Estate's KSA operations. Tracks REGA transaction indicators, Tadawul REIT prices, warehouse listings (Aqar, Bayut, PropertyFinder), MODON announcements, and Knight Frank / CBRE / JLL research. Generates a weekly intelligence brief as a PDF.

**Current deployment: local Mac (development)**. All data stays on your machine. No cloud services, no external accounts, no email distribution. The system produces a PDF brief in `./data/briefs/` that you read locally.

## Quick start

```bash
# 1. Start Postgres + Redis
make up

# 2. Install dependencies (first time)
make install

# 3. Copy env template, fill in Anthropic API key
cp .env.example .env.local
# Edit .env.local: set ANTHROPIC_API_KEY

# 4. Apply database schema
make migrate

# 5. Start the API
make run-api        # terminal 1 — localhost:8000

# 6. Start the frontend
make run-frontend   # terminal 2 — localhost:3000

# 7. Start the scheduler (optional — needed for automatic scraping)
make run-scheduler  # terminal 3 — leave running while Mac is awake
```

## Architecture

```
white-star-hub/
├── backend/
│   ├── app/
│   │   ├── core/         Config, DB, BlobStore abstraction, logging
│   │   ├── models/       SQLAlchemy ORM (market data, ingestion, LLM, auth)
│   │   ├── api/          REST endpoints (Phase 1+)
│   │   ├── ingestion/    Scrapers + outbox reconciler + circuit breakers
│   │   ├── structuring/  Claude client wrapper + PDF pipeline (Phase 2)
│   │   ├── scheduler/    APScheduler 4 jobs
│   │   └── briefing/     Opus 4.6 synthesis + Playwright PDF render (Phase 4)
│   ├── alembic/          Schema migrations (expand/contract only)
│   └── tests/            pytest + VCR cassettes + syrupy snapshots
├── frontend/             Vite 6 + React 19 + ECharts + MapLibre + shadcn/ui
├── data/                 gitignored — local data created at runtime
│   ├── raw/              Raw blobs: {source}/{YYYY}/{MM}/{DD}/{sha1}.{ext}.gz
│   ├── briefs/           Generated PDF briefs: {YYYY}-W{NN}.pdf
│   ├── backups/          pg_dump files: wshub_{timestamp}.sql.gz
│   └── state/            Playwright session state (cookies)
├── infra/postgres/       postgresql.conf
├── docker-compose.yml    Postgres 17 + Redis (local only)
└── Makefile              All commands
```

## Make targets

```
make up              Start Postgres + Redis
make down            Stop Docker services
make migrate         Apply pending migrations
make migrate-create  Create migration (NAME=description)
make run-api         FastAPI on localhost:8000 with hot-reload
make run-scheduler   APScheduler process (leave running in terminal)
make run-frontend    Vite on localhost:3000 with hot-reload
make scrape-tadawul  Fetch today's REIT prices (yfinance)
make scrape-rega     REGA indicator scraper (stub until DevTools capture)
make scrape-aqar     Aqar warehouse listings
make scrape-modon    MODON news page
make scrape-news     Argaam real estate news
make scrape-reports  Download Knight Frank / CBRE / JLL PDFs
make brief           Generate this week's PDF brief → ./data/briefs/
make test            Unit + integration tests (no live HTTP)
make test-canary     Live-URL canary tests
make lint            Ruff lint + format check
make format          Auto-format (Ruff)
make type-check      Mypy strict
make backup          pg_dump → ./data/backups/ (keeps last 14)
make restore-test    Restore latest backup to scratch DB + smoke queries
make logs            Tail ./logs/app.log (formatted via jq)
```

## Data sources

### REGA Open Data request (pending)

**Submitted:** 18 Apr 2026
**Portal:** https://rega.gov.sa/en/open-data/request-open-data/
**Status:** Pending — expected response 30–90 days from submission date

**Requested datasets:**
- Aggregate transaction indicators (count, median price/sqm, total value by district and property type)
- Lease indicators (average asking rent, vacancy rate, absorption by district)
- Geographic reference data (official district boundaries and codes for Riyadh governorate)
- Off-Plan Sales registry (project name, developer, launch date, units sold)

**Scope:** Riyadh governorate, district level, monthly from Jan 2018 to present.

**Current impact:** Transaction count in Workbench evaluate panels and weekly briefs will show zero until REGA responds. The system displays an explicit notice rather than a broken empty state. Secondary sources (Tadawul REITs, Aqar listings, Knight Frank / CBRE / JLL research reports, Argaam news) remain active and are documented in the brief methodology footnote.

**Next step:** Update `app/ingestion/scrapers/rega.py` with the data format once the Open Data response arrives. No scraping of srem.moj.gov.sa — that endpoint is Nafath-gated and out of scope.

---

## Data lineage

Every structured row carries `(source_id, raw_uri, extracted_at, extractor_version, prompt_sha, model_id)`. Raw blobs are at:
```
./data/raw/{source}/{YYYY}/{MM}/{DD}/{sha1}.{ext}.gz
```
The `raw_ingest_outbox` table is the crash-safe link between the blob and its structured rows. The reconciler re-runs extraction for any blob that exists on disk but has no structured rows (handles crashes mid-extraction).

## LLM cost model

| Task | Model | Caching | Batch |
|---|---|---|---|
| Article triage | Haiku 4.5 | No | Yes |
| Arabic→English | Haiku 4.5 | No | Yes |
| PDF extraction | Sonnet 4.6 | Yes (White Star context) | Yes |
| Field extraction | Sonnet 4.6 | Yes | Yes |
| Weekly brief | Opus 4.6 | Yes (1h TTL) | No |
| Ad-hoc Q&A | Sonnet 4.6 | Yes | No |

Every call writes to `llm_calls` (tokens, cost, prompt_sha, cache hit/miss). Daily cap: `CLAUDE_DAILY_BUDGET_USD` (default $5). Monthly hard stop: `CLAUDE_MONTHLY_BUDGET_USD` (default $50) — set a matching workspace cap in the Anthropic Console.

## PDPL note

All data processed is non-personal (REGA aggregates, Tadawul prices, PDF extracts). This system has no external users and holds no Saudi resident PII — PDPL Article 29 transfer restrictions don't apply in this configuration. Document any change when external users are added.

---

## Going to production later

This section documents every stubbed component, where the swap point is, and what changes.

### Blob storage: local → Hetzner S3

**Current:** `LocalBlobStore` writes to `./data/raw/`
**Swap point:** `app/core/storage.py` → `get_blob_store()` factory
**What changes:**
```bash
# .env.local
BLOB_STORE_BACKEND=s3
S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_RAW_BUCKET=ksa-re-raw
```
The `S3BlobStore` class in `storage.py` currently raises `NotImplementedError`. Implement it by wrapping `boto3.client("s3", ...)`. The key convention (`{source}/{YYYY}/{MM}/{DD}/{sha1}.{ext}.gz`) is identical.

### Secret management: .env.local → Infisical

**Current:** pydantic-settings reads `.env.local`
**Swap point:** `app/core/config.py` → `Settings` class `model_config`
**What changes:** Install `infisical-python`, swap `SettingsConfigDict(env_file=...)` for `InfisicalSettings`. All variable names are identical.

### Observability: local logs → Sentry + Better Stack

**Current:** structlog → stdout + `./logs/app.log`
**Swap point:** `app/core/logging.py` → `configure_logging()`; `app/main.py` → `_init_sentry()` (already written, disabled when `SENTRY_DSN` is empty)
**What changes:** Set `SENTRY_DSN` and `BETTER_STACK_TOKEN`. Logs ship to Better Stack via a Vector agent sidecar reading `./logs/app.log`.

### Deployment: local Mac → Hetzner VPS + Coolify

**Current:** uvicorn on localhost, Vite dev server
**Swap point:** Add Dockerfiles (already written for both backend and frontend), `docker-compose.prod.yml`, Caddyfile
**What changes:** Provision CPX31 VPS, run `infra/scripts/provision.sh` (removed from local build but easily restored), add GitHub Actions CI/CD. The Makefile targets remain identical — Coolify calls `docker compose up` on the server.

### Auth: single local user → Authentik SSO

**Current:** fastapi-users with one seeded admin account
**Swap point:** `app/api/routes/auth.py` → swap `fastapi-users` backend for OIDC
**When:** At 10+ users or when SSO is needed. fastapi-users supports OIDC providers.

### Email distribution: none → Microsoft 365 SMTP

**Current:** Brief saved to `./data/briefs/`, no outbound
**Swap point:** `app/briefing/orchestrator.py` → add SMTP send after PDF is written
**What changes:** Set `SMTP_*` env vars, uncomment the mailer in the orchestrator. The Jinja2 template and PDF render path are unchanged.

### Backups: pg_dump → pgBackRest

**Current:** `make backup` → `pg_dump` to `./data/backups/`
**Swap point:** Add pgBackRest config + cron on the production VPS
**RPO/RTO production target:** ~1 min / ~10 min via continuous WAL archiving to Hetzner Object Storage

### Map tiles: OpenFreeMap Liberty (deviation from original spec)

**Original spec** called for MapTiler. The Workbench map uses **OpenFreeMap Liberty** (`https://tiles.openfreemap.org/styles/liberty`) instead — no API key required, identical MapLibre GL JS integration, and free for commercial use.
**Swap point:** `frontend/src/pages/WorkbenchPage.tsx` → `MAP_STYLE` constant at top of file.
**What changes:** Replace the style URL with a MapTiler style URL and add `VITE_MAPTILER_KEY` to `.env.local`.

### Regulatory zones: additional boundaries pending authoritative sources

**Current:** One zone seeded — MODON Riyadh 1st Industrial City (`confidence: low`, approximate polygon from public MODON portal + OSM Relation #2900093). Located in the Al-Malaz / Al-Naseem corridor, northeast Riyadh.
**Polygon accuracy:** LOW — simplified rectangle covering approximate footprint. Do not use for legal or leasing boundary decisions.
**Additional zones will be added when authoritative polygon sources are available:**
- Other MODON industrial cities (Riyadh 2nd, Jeddah, Dammam) — pending MODON GIS data or Royal Commission shapefiles
- King Salman Energy Park (SPARK) — pending Royal Commission for Jubail and Yanbu data
- Economic Cities (KAEC, Neom supply zones) — pending operator GIS releases
- Municipal zoning overlays — pending MOMAH / Balady geospatial API access

Authoritative sources: MODON GIS portal (`modon.gov.sa`), ESRI Saudi Arabia, Saudi Geospatial Authority (SGP), Balady platform.
