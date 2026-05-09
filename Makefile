.PHONY: help up down reset migrate migrate-create run-api run-scheduler run-frontend \
        scrape-tadawul scrape-rega scrape-aqar scrape-modon scrape-news scrape-reports \
        extract-news brief test test-canary lint format type-check backup restore-test logs clean \
        seed-admin seed-districts seed-default-sites

# Load .env.local if it exists — exposes vars to make recipes
-include .env.local

PYTHON  := .venv/bin/python
PYTEST  := .venv/bin/pytest
RUFF    := .venv/bin/ruff
MYPY    := .venv/bin/mypy
UV      := .venv/bin/uv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ─────────────────────────────────────────────────────────────

up: ## Start Postgres + Redis in Docker
	docker compose up -d
	@echo "Postgres on localhost:5432, Redis on localhost:6379"
	@docker compose ps

down: ## Stop Docker services (data preserved)
	docker compose down

reset: ## Destroy and recreate Docker volumes (drops all data)
	docker compose down -v
	docker compose up -d

# ── Database ───────────────────────────────────────────────────────────────────

migrate: ## Apply pending Alembic migrations
	cd backend && $(PYTHON) -m alembic upgrade head

migrate-create: ## Create a new Alembic migration (NAME= required)
	@test -n "$(NAME)" || (echo "Usage: make migrate-create NAME=describe_the_change" && exit 1)
	cd backend && $(PYTHON) -m alembic revision --autogenerate -m "$(NAME)"

# ── API server ─────────────────────────────────────────────────────────────────

run-api: ## Start FastAPI dev server with hot-reload on :8000
	cd backend && $(PYTHON) -m uvicorn app.main:app \
	  --host 127.0.0.1 --port 8000 --reload --reload-dir app

# ── Scheduler ─────────────────────────────────────────────────────────────────

run-scheduler: ## Start APScheduler process (run in a separate terminal tab)
	cd backend && $(PYTHON) -m app.scheduler.main

# ── Frontend ───────────────────────────────────────────────────────────────────

run-frontend: ## Start Vite dev server on :3000
	cd frontend && npm run dev

# ── Scrapers (run one-off) ─────────────────────────────────────────────────────

scrape-tadawul: ## Fetch today's REIT prices via yfinance
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.tadawul

scrape-rega: ## Run REGA indicator scraper (stub until DevTools capture)
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.rega

scrape-aqar: ## Scrape Aqar.fm warehouse listings (Riyadh industrial districts)
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.aqar

scrape-modon: ## Scrape MODON news page
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.modon

scrape-news: ## Scrape Argaam real estate news
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.news

scrape-reports: ## Download Knight Frank / CBRE / JLL PDF reports
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.knight_frank

extract-pdf: ## Extract structured facts from a PDF report (FILE= required)
	@test -n "$(FILE)" || (echo "Usage: make extract-pdf FILE=path/to/report.pdf" && exit 1)
	cd backend && $(PYTHON) -m app.pdf.extractor $(FILE)

# ── LLM pipeline ──────────────────────────────────────────────────────────────

fetch-bodies: ## Fetch full article bodies for high-relevance articles (requires SCRAPER_LIVE_MODE=true)
	cd backend && SCRAPER_LIVE_MODE=true $(PYTHON) -m app.ingestion.scrapers.news_body

extract-news: ## Run Haiku triage + Sonnet extraction on unprocessed news articles
	cd backend && $(PYTHON) -c "import asyncio; from app.ingestion.extractors.news import run_news_extractor; asyncio.run(run_news_extractor())"

# ── Brief ─────────────────────────────────────────────────────────────────────

brief: ## Generate this week's intelligence brief (requires ANTHROPIC_API_KEY)
	cd backend && $(PYTHON) -m app.briefing.orchestrator

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## Run unit + integration tests (no live HTTP calls)
	cd backend && $(PYTEST) -v -m "not canary" --tb=short tests/

test-canary: ## Run canary tests against live URLs (requires SCRAPER_LIVE_MODE=true)
	cd backend && SCRAPER_LIVE_MODE=true $(PYTEST) -v -m canary --timeout=60 tests/

test-golden: ## Run golden set regression tests
	cd backend && $(PYTEST) -v -m golden tests/

# ── Code quality ──────────────────────────────────────────────────────────────

lint: ## Ruff lint + format check
	cd backend && $(RUFF) check app tests && $(RUFF) format --check app tests

format: ## Auto-format with Ruff
	cd backend && $(RUFF) format app tests && $(RUFF) check --fix app tests

type-check: ## Mypy strict type check
	cd backend && $(MYPY) app

# ── Backup / restore ──────────────────────────────────────────────────────────

backup: ## pg_dump → ./data/backups/ (keeps last 14)
	@mkdir -p data/backups
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	FILE="data/backups/wshub_$${TIMESTAMP}.sql.gz"; \
	PGPASSWORD=$${POSTGRES_PASSWORD:-wspass} pg_dump \
	  -h localhost -U $${POSTGRES_USER:-wsuser} $${POSTGRES_DB:-wshub} \
	  --format=custom --compress=9 > "$$FILE" && \
	echo "Backup saved: $$FILE ($$(du -sh $$FILE | cut -f1))"
	@ls -t data/backups/*.sql.gz | tail -n +15 | xargs rm -f 2>/dev/null || true
	@echo "Kept last 14 backups (oldest removed if >14 existed)"

restore-test: ## Restore latest backup to scratch DB + run smoke queries
	@LATEST=$$(ls -t data/backups/*.sql.gz 2>/dev/null | head -1); \
	test -n "$$LATEST" || (echo "No backups found in data/backups/" && exit 1); \
	echo "Testing restore of: $$LATEST"; \
	PGPASSWORD=$${POSTGRES_PASSWORD:-wspass} psql \
	  -h localhost -U $${POSTGRES_USER:-wsuser} postgres \
	  -c "DROP DATABASE IF EXISTS wshub_restore_test" 2>/dev/null; \
	PGPASSWORD=$${POSTGRES_PASSWORD:-wspass} psql \
	  -h localhost -U $${POSTGRES_USER:-wsuser} postgres \
	  -c "CREATE DATABASE wshub_restore_test"; \
	PGPASSWORD=$${POSTGRES_PASSWORD:-wspass} pg_restore \
	  -h localhost -U $${POSTGRES_USER:-wsuser} \
	  -d wshub_restore_test "$$LATEST"; \
	echo "Smoke queries:"; \
	PGPASSWORD=$${POSTGRES_PASSWORD:-wspass} psql \
	  -h localhost -U $${POSTGRES_USER:-wsuser} wshub_restore_test \
	  -c "SELECT 'transactions' AS tbl, count(*) FROM transactions UNION ALL SELECT 'reit_snapshots', count(*) FROM reit_snapshots UNION ALL SELECT 'listings', count(*) FROM listings;"; \
	PGPASSWORD=$${POSTGRES_PASSWORD:-wspass} psql \
	  -h localhost -U $${POSTGRES_USER:-wsuser} postgres \
	  -c "DROP DATABASE wshub_restore_test"; \
	echo "Restore test PASSED"

# ── Logs ──────────────────────────────────────────────────────────────────────

logs: ## Tail the application log (pretty-printed JSON via jq)
	@command -v jq >/dev/null 2>&1 && \
	  tail -f logs/app.log | jq -r '[.timestamp, .level, .logger, .event] | @tsv' || \
	  tail -f logs/app.log

# ── Auth ──────────────────────────────────────────────────────────────────────

seed-admin: ## Create the first admin user (reads ADMIN_EMAIL / ADMIN_PASSWORD from .env.local)
	cd backend && $(PYTHON) -m app.scripts.seed_admin

seed-districts: ## Populate DistrictAlias table with Riyadh industrial district names/aliases
	cd backend && $(PYTHON) -m app.scripts.seed_districts

seed-default-sites: ## Seed MODON Riyadh 1 as a default saved site for the admin user
	cd backend && $(PYTHON) -m app.scripts.seed_default_sites

# ── Setup ─────────────────────────────────────────────────────────────────────

install: ## Install Python deps (backend) + JS deps (frontend)
	cd backend && python3 -m venv .venv && \
	  .venv/bin/pip install -q -e ".[dev]"
	cd frontend && npm install

# ── Clean ─────────────────────────────────────────────────────────────────────

clean: ## Remove Python cache files and build artifacts
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find backend -name "*.pyc" -delete 2>/dev/null || true
	rm -rf frontend/dist
