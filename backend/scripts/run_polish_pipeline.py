#!/usr/bin/env python
"""End-to-end Polish news ingestion pipeline.

Runs all 4 stages in sequence and prints a full report:
  Stage 1: Scrape  — Eurobuild CEE + Money.pl (last 30 days)
  Stage 2: Bodies  — Fetch full article text for triage-eligible articles
  Stage 3: Triage  — Haiku 4.5 Warsaw relevance scoring (threshold ≥ 0.6)
  Stage 4: Extract — Sonnet 4.6 fact extraction into 8 typed tables

Usage:
  cd /Users/karol/wsre-intelligence/backend
  SCRAPER_LIVE_MODE=true .venv/bin/python scripts/run_polish_pipeline.py [--no-scrape] [--no-bodies]

Options:
  --no-scrape   Skip scraping stage (re-use existing articles in DB)
  --no-bodies   Skip body fetch stage
  --no-extract  Skip extraction stage (triage only)
  --report-only Just print current DB stats, no pipeline run
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

# ── Bootstrap Django-style app import path ─────────────────────────────────────
import os

# Ensure we can import from app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _report_db_stats(session) -> None:
    """Print full pipeline stats from the DB."""
    from sqlalchemy import text

    sources_sql = "('eurobuild_cee', 'money_pl_nieruch')"

    print("\n" + "=" * 65)
    print("WARSAW NEWS PIPELINE — DB STATS")
    print("=" * 65)

    # Article counts
    r = await session.execute(text(f"""
        SELECT
            source,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE relevance_score IS NULL) AS unscored,
            COUNT(*) FILTER (WHERE relevance_score >= 0.6) AS high_relevance,
            COUNT(*) FILTER (WHERE relevance_score >= 0.4 AND relevance_score < 0.6) AS medium_relevance,
            COUNT(*) FILTER (WHERE relevance_score < 0.4 AND relevance_score IS NOT NULL) AS low_relevance,
            COUNT(*) FILTER (WHERE body_en IS NOT NULL OR body_ar IS NOT NULL) AS has_body,
            COUNT(*) FILTER (WHERE structured_facts != '{{}}'::jsonb) AS extracted,
            ROUND(AVG(relevance_score)::numeric, 3) AS avg_score
        FROM news_articles
        WHERE source IN {sources_sql}
        GROUP BY source
        ORDER BY source
    """))
    rows = r.fetchall()

    if not rows:
        print("\n  No Polish news articles in DB yet.")
    else:
        print("\nARTICLES PER SOURCE:")
        for row in rows:
            print(f"  {row.source}:")
            print(f"    Total:          {row.total}")
            print(f"    Unscored:       {row.unscored}")
            print(f"    High rel (≥0.6): {row.high_relevance}  (promoted to extraction)")
            print(f"    Med rel (0.4-0.6): {row.medium_relevance}")
            print(f"    Low rel (<0.4): {row.low_relevance}")
            print(f"    Has body:       {row.has_body}")
            print(f"    Extracted:      {row.extracted}")
            print(f"    Avg score:      {row.avg_score}")

    # Facts per table
    fact_tables = [
        "supply_events",
        "capital_markets_events",
        "regulatory_events",
        "macro_signals",
        "tenant_signals",
        "demand_signals",
        "market_commentary",
        "infrastructure_events",
    ]

    print("\nFACTS IN TYPED TABLES (from Polish articles):")
    total_facts = 0
    fact_counts: dict[str, int] = {}
    for table in fact_tables:
        try:
            # Join via article_id to filter to Polish sources
            r2 = await session.execute(text(f"""
                SELECT COUNT(*) AS cnt
                FROM {table} f
                JOIN news_articles a ON a.id = f.article_id
                WHERE a.source IN {sources_sql}
            """))
            cnt = r2.scalar() or 0
        except Exception:
            cnt = 0
        fact_counts[table] = cnt
        total_facts += cnt
        print(f"  {table:<30} {cnt:>5}")

    print(f"  {'TOTAL':<30} {total_facts:>5}")

    print("\nFACT DISTRIBUTION (all sources, for context):")
    for table in fact_tables:
        try:
            r3 = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            cnt_all = r3.scalar() or 0
            print(f"  {table:<30} {cnt_all:>5} (all sources)")
        except Exception:
            pass

    return fact_counts


async def _print_sample_facts(session) -> None:
    """Print 5 sample extracted facts from Polish articles."""
    from sqlalchemy import text

    sources_sql = "('eurobuild_cee', 'money_pl_nieruch')"
    fact_tables = [
        ("supply_events", "developer, project_name, location_description, asset_class, source_citation"),
        ("capital_markets_events", "event_type, entity, value_sar, source_citation"),
        ("regulatory_events", "authority, summary, source_citation"),
        ("macro_signals", "indicator, period, value, direction, source_citation"),
        ("tenant_signals", "tenant_name, industry, event_type, geography, source_citation"),
        ("demand_signals", "sector, metric, value, geography, source_citation"),
        ("market_commentary", "source_authority, topic, quote_under_15_words, source_citation"),
        ("infrastructure_events", "project, infra_type, location, completion_date, source_citation"),
    ]

    print("\n" + "=" * 65)
    print("SAMPLE EXTRACTED FACTS (up to 1 per type from Polish articles)")
    print("=" * 65)

    samples_printed = 0
    for table, cols in fact_tables:
        if samples_printed >= 5:
            break
        try:
            r = await session.execute(text(f"""
                SELECT f.id, f.confidence, {', '.join(f'f.{c.strip()}' for c in cols.split(','))},
                       a.source, a.title_en, a.url
                FROM {table} f
                JOIN news_articles a ON a.id = f.article_id
                WHERE a.source IN {sources_sql}
                  AND f.confidence >= 4
                ORDER BY f.created_at DESC
                LIMIT 1
            """))
            row = r.fetchone()
            if not row:
                continue
            print(f"\n[{table}] (id={row.id}, confidence={row.confidence})")
            print(f"  Source article: [{row.source}] {row.title_en or '(no title)'}")
            print(f"  URL: {row.url or 'n/a'}")
            print("  Fact data:")
            for col in cols.split(","):
                col = col.strip()
                val = getattr(row, col, None)
                if val is not None:
                    print(f"    {col}: {val}")
            samples_printed += 1
        except Exception as exc:
            print(f"  [{table}] query failed: {exc}")

    if samples_printed == 0:
        print("  No promoted facts found yet (confidence < 4 or tables empty).")


async def main() -> None:
    args = set(sys.argv[1:])
    report_only = "--report-only" in args
    skip_scrape = "--no-scrape" in args or report_only
    skip_bodies = "--no-bodies" in args or report_only
    skip_extract = "--no-extract" in args or report_only

    from app.core.logging import configure_logging
    configure_logging()

    from app.core.database import AsyncSessionFactory, engine
    from sqlalchemy import text as sa_text

    # Verify DB connection
    async with engine.connect() as conn:
        await conn.execute(sa_text("SELECT 1"))
    print("Database: connected")

    # ── Stage 1: Scrape ────────────────────────────────────────────────────────
    if not skip_scrape:
        print("\n" + "─" * 65)
        print("STAGE 1: SCRAPING")
        print("─" * 65)

        # Temporarily override SCRAPER_LIVE_MODE for this run
        from app.core.config import settings
        original_mode = settings.scraper_live_mode
        # Force live mode for this script
        object.__setattr__(settings, "scraper_live_mode", True)

        try:
            from app.ingestion.scrapers.polish_news import run_polish_news_scraper
            scrape_results = await run_polish_news_scraper()
            for source, count in scrape_results.items():
                print(f"  {source}: {count} articles scraped")
            total_scraped = sum(scrape_results.values())
            print(f"  Total scraped: {total_scraped}")
        finally:
            object.__setattr__(settings, "scraper_live_mode", original_mode)
    else:
        print("\n[Scraping skipped]")

    # ── Stage 2: Body fetch ────────────────────────────────────────────────────
    if not skip_bodies:
        print("\n" + "─" * 65)
        print("STAGE 2: BODY FETCH")
        print("─" * 65)

        # Patch the body fetcher to also process Polish sources
        # (it already filters relevance >= 0.35, which is fine;
        #  we set relevance=None articles will be skipped until after triage)
        # First run triage on unscored articles, then fetch bodies for passing ones.

        # Mini-triage pass to score articles so body fetch picks them up
        async with AsyncSessionFactory() as session:
            from app.ingestion.extractors.warsaw_news import run_warsaw_triage
            triaged = await run_warsaw_triage(session)
            print(f"  Pre-body triage: {triaged} articles scored")

        from app.core.config import settings
        object.__setattr__(settings, "scraper_live_mode", True)
        try:
            from app.ingestion.scrapers.news_body import run_news_body_fetcher
            updated = await run_news_body_fetcher()
            print(f"  Bodies fetched: {updated}")
        finally:
            object.__setattr__(settings, "scraper_live_mode", original_mode)
    else:
        print("\n[Body fetch skipped]")

    # ── Stage 3: Full triage ───────────────────────────────────────────────────
    print("\n" + "─" * 65)
    print("STAGE 3: TRIAGE (Warsaw Haiku)")
    print("─" * 65)

    total_triaged = 0
    # Run multiple batches until all unscored articles are processed
    for batch in range(1, 20):  # up to 1000 articles (50 * 20)
        async with AsyncSessionFactory() as session:
            from app.ingestion.extractors.warsaw_news import run_warsaw_triage
            n = await run_warsaw_triage(session)
        if n == 0:
            break
        total_triaged += n
        print(f"  Batch {batch}: {n} articles triaged (running total: {total_triaged})")
    print(f"  Total triaged: {total_triaged}")

    # ── Stage 4: Body fetch (post-triage, for any newly scored articles) ───────
    if not skip_bodies:
        print("\n" + "─" * 65)
        print("STAGE 4a: BODY FETCH (post-triage top-up)")
        print("─" * 65)
        from app.core.config import settings
        object.__setattr__(settings, "scraper_live_mode", True)
        try:
            from app.ingestion.scrapers.news_body import run_news_body_fetcher
            updated2 = await run_news_body_fetcher()
            print(f"  Bodies fetched: {updated2}")
        finally:
            object.__setattr__(settings, "scraper_live_mode", original_mode)

    # ── Stage 4b: Extraction ───────────────────────────────────────────────────
    if not skip_extract:
        print("\n" + "─" * 65)
        print("STAGE 4: EXTRACTION (Warsaw Sonnet)")
        print("─" * 65)

        total_extracted = 0
        for batch in range(1, 30):  # up to 600 articles (20 * 30)
            async with AsyncSessionFactory() as session:
                from app.ingestion.extractors.warsaw_news import run_warsaw_extraction
                n = await run_warsaw_extraction(session)
            if n == 0:
                break
            total_extracted += n
            print(f"  Batch {batch}: {n} articles extracted (running total: {total_extracted})")
        print(f"  Total extracted: {total_extracted}")
    else:
        print("\n[Extraction skipped]")

    # ── Report ─────────────────────────────────────────────────────────────────
    async with AsyncSessionFactory() as session:
        fact_counts = await _report_db_stats(session)
        total_facts = sum(fact_counts.values()) if fact_counts else 0

    async with AsyncSessionFactory() as session:
        await _print_sample_facts(session)

    print("\n" + "=" * 65)
    print("PIPELINE COMPLETE")
    print(f"  Total promoted facts: {total_facts}")
    if total_facts < 20:
        print(f"  WARNING: Only {total_facts} facts promoted (target: ≥30).")
        print("  Suggestion: extend lookback to 60 days with --lookback=60 or check site parsers.")
    elif total_facts < 30:
        print(f"  INFO: {total_facts} facts — below 30 target. Consider 60-day window.")
    else:
        print(f"  Target met: {total_facts} >= 30 facts. Ready for 4B synthesis.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
