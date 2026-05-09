# WSRE Intelligence

Warsaw real estate market intelligence platform. Forked from white-star-hub on 2026-05-09.

## Status

Phase 1 complete: clean fork, Saudi scrapers disabled, fresh DB (`wsre` / `wsre_test`), app boots.

## Quick start

```bash
# 1. Start Postgres + Redis (or use local Postgres directly)
make up

# 2. Install dependencies (first time)
make install

# 3. Copy env template, fill in Anthropic API key
cp .env.example .env.local
# Edit .env.local: set ANTHROPIC_API_KEY

# 4. Apply database schema (14 migrations)
make migrate

# 5. Start the API
make run-api        # terminal 1 — localhost:8000

# 6. Start the frontend
make run-frontend   # terminal 2 — localhost:5173

# 7. Start the scheduler (optional)
make run-scheduler  # terminal 3
```

## Architecture

Inherited from white-star-hub. See source repo for full documentation.
Phase 2 will retarget data sources, ingestion logic, and taxonomies for Warsaw.
