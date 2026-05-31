# Contributing & Local Setup

This document is for reviewers, peer reviewers, and anyone reproducing the project locally.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Project developed on 3.14; 3.11+ should work |
| Node.js | 18+ | 20 LTS recommended |
| PostgreSQL | 15+ | With PostGIS 3.4+ extension |
| Redis | 7+ | Used by the APScheduler job store |
| Anthropic API key | — | Required for AI pipeline features |
| Polish IP / VPN | — | Required for live Warsaw BGiK WMS layers |

> **WMS note:** The Warsaw municipal WMS at `wms.um.warszawa.pl` geo-restricts to Polish IP addresses. Without a Polish IP, the Workbench map will show the basemap and POI layers but not the MPZP zoning overlay layers. The Plot Evaluation panel (Sections A–I) functions independently of WMS.

---

## 1. Clone the repository

```bash
git clone https://github.com/kblasins/wsre-intelligence.git
cd wsre-intelligence
```

---

## 2. Database setup

```bash
# Create the database and user (adjust if Postgres is running differently)
psql -U postgres -c "CREATE USER wsuser WITH PASSWORD 'wspass';"
psql -U postgres -c "CREATE DATABASE wsre OWNER wsuser;"
psql -U postgres -c "CREATE DATABASE wsre_test OWNER wsuser;"

# Enable PostGIS (run as superuser)
psql -U postgres wsre -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -U postgres wsre -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql -U postgres wsre -c "CREATE EXTENSION IF NOT EXISTS btree_gin;"
```

---

## 3. Backend setup

```bash
cd backend

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
# or: pip install -e ".[dev]"

# Copy and edit environment file
cp ../.env.example .env.local
# Required edits in .env.local:
#   ANTHROPIC_API_KEY=sk-ant-...  (your key)
#   DATABASE_URL=postgresql+asyncpg://wsuser:wspass@localhost:5432/wsre
```

---

## 4. Run migrations

```bash
# From backend/ with .venv active
alembic upgrade head
```

This applies all 23 migrations and seeds the demo plot data (ul. Towarowa 28 — Wola) including:
- Plot zoning seed (MPZP parameters, function code, FAR, height)
- Land comparables seed (10 demo transactions)
- Demographics seed
- Infrastructure seed
- Regulatory event seed

---

## 5. Seed the admin user

```bash
# From backend/ with .venv active
python -m app.scripts.seed_admin
```

Creates the login user from `.env.local` values (`ADMIN_EMAIL` / `ADMIN_PASSWORD`). Default in `.env.example` is `admin@local` / `change-me-immediately` — override before seeding.

---

## 6. (Optional) Bootstrap ingestion data

The repository ships with the demo plot seed data baked into migrations, so the Workbench demo works without running ingestion. To populate the full Jawność dataset and POI data:

```bash
# Ingest Warsaw POIs from OpenStreetMap (~5 minutes)
python -m app.ingestion.scrapers.osm_pois

# Discover and ingest Jawność datasets (~2-4 hours, 16,175 datasets)
# WARNING: large download, requires stable connection
python -m app.ingestion.scrapers.jawnosc --limit 200  # smaller test run
```

The primary pricing pipeline downloads datasets from dane.gov.pl. A full run ingests ~85,000 dwelling rows. The `--limit` flag runs a smaller subset for reproducibility testing.

---

## 7. Start the backend

```bash
# From backend/ with .venv active
uvicorn app.main:app --port 8000 --reload
```

Verify at: `http://localhost:8000/api/health`
Expected response: `{"status": "ok", "version": "0.1.0", "env": "development"}`

---

## 8. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. The Vite dev server proxies all `/api/*` requests to `localhost:8000`.

---

## Environment variables

All variables are set in `backend/.env.local` (gitignored). Reference: `backend/.env.example`.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL asyncpg connection string |
| `ANTHROPIC_API_KEY` | Yes (for AI features) | Anthropic API key for Haiku/Sonnet/Opus |
| `SECRET_KEY` | Yes | JWT signing secret (any random string for local dev) |
| `ADMIN_EMAIL` | Yes | Seeded admin user email |
| `ADMIN_PASSWORD` | Yes | Seeded admin user password |
| `REDIS_URL` | No | Redis URL for scheduler (defaults to `redis://localhost:6379/0`) |
| `CLAUDE_MONTHLY_BUDGET_USD` | No | Monthly AI spend cap (default: $50) |
| `SCRAPER_LIVE_MODE` | No | `true` to enable live scraping HTTP calls |
| `ORS_API_KEY` | No | OpenRouteService key for isochrone endpoint |

---

## Reproducing the demo plot

After running migrations, the ul. Towarowa 28 — Wola demo plot is fully seeded. To verify all 9 sections load:

1. Start backend + frontend
2. Navigate to `http://localhost:5173/login`
3. Log in with your `ADMIN_EMAIL` / `ADMIN_PASSWORD` credentials
4. Click **"ul. Towarowa 28 — Wola"** in the Saved Deals sidebar
5. The right panel should populate all 9 sections within ~2 seconds

**Expected Section A values:**
- Plan: `rej. ul. Żelaznej cz. północna A`
- Function: `U(MW)` (mixed-use: services + residential)
- Max FAR: 12
- Max height: 55m

**Expected Section I values:**
- Residual land value: ~PLN 61,868/m²
- Build cost: 7,500 PLN/m² PUM (U(MW) function code)
- Exit methodology: 60% residential + 40% commercial blended

**WMS layers (Polish IP required):**
- Enable "MPZP coverage" and "MPZP function" in the Plots & Zoning layer group
- Zoom to the Wola district
- Click anywhere on the map to test GetFeatureInfo popup

---

## Known reproducibility constraints

- **Polish IP for WMS:** See note above. WMS features degrade gracefully without it.
- **Test suite:** 226 backend tests currently error at setup due to a missing `psycopg2` dependency in the test fixture (pre-existing from the Saudi fork; the app uses `asyncpg` in production). See [LIMITATIONS.md](./LIMITATIONS.md).
- **Full Jawność ingestion:** Takes 2–4 hours and ~500MB of disk. Not required for the demo.
- **News scraping:** Live scraping requires `SCRAPER_LIVE_MODE=true`. Rate limits apply.
