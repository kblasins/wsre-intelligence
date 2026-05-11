"""Sub-phase 2A discovery runner: populate jawnosc_developers registry.

Run from the backend/ directory:
    python scripts/discover_jawnosc.py [--max-pages N] [--no-probe]

Options:
    --max-pages N   Limit API pages (100 datasets/page). Omit for full discovery.
    --no-probe      Skip feed sampling (faster; Warsaw detection via title only).
    --max-probe N   Max number of Warsaw-candidate feeds to probe (default 200).
    --report-only   Print report without writing to DB.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure backend/app is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.ingestion.scrapers.jawnosc import (
    WARSAW_DISTRICTS,
    DaneGovClient,
    JawNoscDiscovery,
    run_discovery,
)

log = structlog.get_logger(__name__)


def _make_async_url(raw: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return raw.replace(prefix, "postgresql+asyncpg://", 1)
    return raw


async def upsert_records(
    session: AsyncSession, records: list[dict]
) -> int:
    """Upsert records into jawnosc_developers. Returns count upserted."""
    from sqlalchemy import text

    inserted = 0
    for r in records:
        districts = r.get("coverage_districts") or []
        modified = r.get("dataset_modified")
        if isinstance(modified, str) and modified:
            try:
                modified = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            except ValueError:
                modified = None

        await session.execute(
            text("""
                INSERT INTO jawnosc_developers (
                    developer_name, developer_id, institution_id,
                    dataset_url, feed_url, schema_version,
                    sync_status, coverage_districts,
                    active_units_count, city_hq, dataset_modified,
                    data_format, updated_at
                ) VALUES (
                    :developer_name, :developer_id, :institution_id,
                    :dataset_url, :feed_url, :schema_version,
                    :sync_status, :coverage_districts,
                    :active_units_count, :city_hq, :dataset_modified,
                    :data_format, NOW()
                )
                ON CONFLICT (developer_id)
                DO UPDATE SET
                    developer_name      = EXCLUDED.developer_name,
                    feed_url            = EXCLUDED.feed_url,
                    schema_version      = COALESCE(EXCLUDED.schema_version, jawnosc_developers.schema_version),
                    sync_status         = EXCLUDED.sync_status,
                    coverage_districts  = EXCLUDED.coverage_districts,
                    active_units_count  = EXCLUDED.active_units_count,
                    city_hq             = EXCLUDED.city_hq,
                    dataset_modified    = EXCLUDED.dataset_modified,
                    data_format         = EXCLUDED.data_format,
                    updated_at          = NOW()
            """),
            {
                "developer_name": r["developer_name"],
                "developer_id": r["developer_id"],
                "institution_id": r.get("institution_id") or None,
                "dataset_url": r.get("dataset_url") or "",
                "feed_url": r.get("feed_url"),
                "schema_version": r.get("schema_version"),
                "sync_status": r.get("sync_status", "pending"),
                "coverage_districts": districts if districts else None,
                "active_units_count": r.get("active_units_count", 0),
                "city_hq": r.get("city_hq"),
                "dataset_modified": modified,
                "data_format": r.get("data_format"),
            },
        )
        inserted += 1

    await session.commit()
    return inserted


def print_report(result: dict) -> None:
    stats = result["stats"]
    records = result["records"]

    print("\n" + "=" * 70)
    print("JAWNOSC DISCOVERY REPORT — Sub-phase 2A")
    print(f"Run at: {datetime.now(UTC).isoformat()}")
    print("=" * 70)
    print(f"\nTotal datasets discovered (nationally): {stats['total_discovered']:,}")
    print(f"  Active (modified ≤30 days):            {stats['active']:,}")
    print(f"  Stale (>30 days since update):         {stats['stale']:,}")
    print(f"  Unreachable feed:                      {stats['unreachable']:,}")
    print(f"  Schema error:                          {stats['schema_error']:,}")
    print(f"\nWarsaw detection:")
    print(f"  Warsaw candidates (title heuristic):   {stats['warsaw_candidates_by_title']:,}")
    print(f"  Warsaw confirmed (data sampling):      {stats['warsaw_confirmed_by_data']:,}")

    # Warsaw-active breakdown
    warsaw_records = [r for r in records if r.get("is_warsaw_candidate") or r.get("coverage_districts")]
    active_warsaw = [r for r in warsaw_records if r.get("sync_status") == "active"]
    stale_warsaw = [r for r in warsaw_records if r.get("sync_status") == "stale"]

    print(f"\nWarsaw-active developers (active feed + Warsaw signal): {len(active_warsaw)}")
    print(f"Warsaw-stale developers:                                  {len(stale_warsaw)}")

    print("\nSync status distribution:")
    from collections import Counter
    status_counts = Counter(r["sync_status"] for r in records)
    for status, count in sorted(status_counts.items()):
        print(f"  {status:<20} {count:,}")

    print("\n10 sample Warsaw developer rows:")
    print("-" * 70)
    sample = active_warsaw[:10] or warsaw_records[:10]
    for r in sample:
        name = r["developer_name"][:55]
        status = r["sync_status"]
        districts = ", ".join(r.get("coverage_districts") or []) or "–"
        units = r.get("active_units_count", 0)
        fmt = r.get("data_format", "?")
        print(f"  [{status:12s}] {name}")
        print(f"    districts={districts}  units={units}  format={fmt}")
        print(f"    feed: {(r.get('feed_url') or '–')[:70]}")
    print("=" * 70 + "\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Jawnosc Sub-phase 2A discovery")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Limit number of API pages (100 records each)")
    parser.add_argument("--no-probe", action="store_true",
                        help="Skip live feed sampling")
    parser.add_argument("--max-probe", type=int, default=200,
                        help="Max feeds to probe for Warsaw (default 200)")
    parser.add_argument("--report-only", action="store_true",
                        help="Print report without writing to DB")
    args = parser.parse_args()

    print(f"Starting Jawnosc discovery (max_pages={args.max_pages}, probe={not args.no_probe})")

    result = await run_discovery(
        max_pages=args.max_pages,
        probe=not args.no_probe,
        max_probe=args.max_probe,
        parallel_probe=True,
    )

    print_report(result)

    if not args.report_only:
        db_url = _make_async_url(str(settings.database_url))
        engine = create_async_engine(db_url, echo=False)
        AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)
        async with AsyncSessionFactory() as session:
            n = await upsert_records(session, result["records"])
            print(f"Upserted {n:,} records into jawnosc_developers")
        await engine.dispose()
    else:
        print("[report-only mode — nothing written to DB]")


if __name__ == "__main__":
    asyncio.run(main())
