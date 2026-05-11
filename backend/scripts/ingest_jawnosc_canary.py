"""Sub-phase 2B canary ingestion: 30 priority Warsaw developers.

Steps performed:
  1. Load developer_firm_aliases.json → build/update developer_firms table
  2. Map jawnosc_developers rows to developer_firms via fuzzy normalization
  3. For each of the 30 priority firms, find all matching datasets in jawnosc_developers
  4. Re-probe stale feeds using feed-internal freshness (lastUpdateDate / dataDate)
  5. Parse the latest data file (CSV / XLSX / JSON) via jawnosc_parser
  6. Upsert into primary_pricing, maintaining price_history for changed prices
  7. Report: per-firm row counts, schema_errors, district distribution, spot-check 3 units

Run:
    python scripts/ingest_jawnosc_canary.py [--dry-run] [--firm NAME]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import re as _re

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.ingestion.scrapers.jawnosc import DaneGovClient, FeedCatalogParser
from app.ingestion.scrapers.jawnosc_parser import (
    ParsedDwelling,
    parse_feed_file,
    resolve_warsaw_district,
)

log = structlog.get_logger(__name__)

# ── Priority firms for 2B canary ──────────────────────────────────────────────

PRIORITY_FIRMS = [
    "Dom Development", "Atal", "Robyg", "Echo Investment", "Develia",
    "Marvipol Development", "Murapol", "Yareal Polska", "Matexi Polska",
    "Okam Capital", "Archicom", "Lokum Deweloper", "Victoria Dom",
    "YIT Polska", "Budimex Nieruchomości", "BPI Real Estate", "Polnord",
    "JW Construction", "Asbud", "Spravia", "Cordia Polska",
    "Eiffage Immobilier Polska", "Cavatina Holding", "Ronson Development",
    "Inpro", "ED Invest", "Profbud", "Modecom", "Trei Real Estate",
    "Yareal Polska",
]

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ALIASES_FILE = DATA_DIR / "developer_firm_aliases.json"


# ── DB URL helper ──────────────────────────────────────────────────────────────

def _make_async_url(raw: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return raw.replace(prefix, "postgresql+asyncpg://", 1)
    return raw


# ── Name normalization ─────────────────────────────────────────────────────────

# Legal forms to strip when normalizing
_LEGAL_FORMS = re.compile(
    r"\b(spółka z ograniczoną odpowiedzialnością|sp\. z o\.o\.|sp\. z o\. o\.|"
    r"spolka z ograniczona odpowiedzialnoscia|s\.a\.|sa\b|spółka akcyjna|"
    r"spółka komandytowa|sp\.k\.|s\.k\.|"
    r"w 20\d\d r\.|w 20\d\d roku|20\d\d r\.|2025|2026|"
    r"projekt \d+|spv \d+|etap [ivxlcdm]+|etap \d+|"
    r"ceny ofertowe mieszkan dewelopera|ceny ofertowe dla nieruchomosci w inwestycji|"
    r"ceny ofertowe mieszkan|ceny ofertowe domow)\b",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")


def _strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_firm_name(raw: str) -> str:
    """Strip legal forms, SPV suffixes, diacritics, lowercase → canonical key."""
    s = raw.lower()
    s = _strip_diacritics(s)
    s = _LEGAL_FORMS.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
    # Remove trailing punctuation
    s = s.strip(".,;:-")
    return s


def _firm_initials(name: str, overrides: dict[str, str]) -> str:
    if name in overrides:
        return overrides[name]
    words = [w for w in name.split() if w and w[0].isupper()]
    return "".join(w[0] for w in words)[:3].upper() or name[:2].upper()


# ── Load aliases ──────────────────────────────────────────────────────────────

def load_aliases() -> tuple[dict[str, str], dict[str, str]]:
    """Returns (alias_map, initials_overrides)."""
    if not ALIASES_FILE.exists():
        return {}, {}
    with ALIASES_FILE.open() as f:
        data = json.load(f)
    overrides = data.pop("_initials_overrides", {})
    data.pop("_comment", None)
    return data, overrides


# ── Feed freshness check ──────────────────────────────────────────────────────

def _extract_freshness_from_catalog(xml_bytes: bytes) -> date | None:
    """Return the most recent dataDate found in the XML catalog."""
    from xml.etree import ElementTree as ET
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    dates: list[date] = []
    for el in root.iter():
        if "dataDate" in el.tag or "lastUpdateDate" in el.tag or "data_date" in el.tag:
            if el.text:
                try:
                    d = datetime.fromisoformat(el.text.strip()[:10]).date()
                    dates.append(d)
                except ValueError:
                    pass
    return max(dates) if dates else None


def classify_freshness(most_recent_date: date | None) -> str:
    if most_recent_date is None:
        return "unknown"
    delta = (date.today() - most_recent_date).days
    if delta <= 30:
        return "active"
    elif delta <= 90:
        return "recently_active"
    else:
        return "stale"


# ── Developer firms population ────────────────────────────────────────────────

async def populate_developer_firms(
    session: AsyncSession,
    alias_map: dict[str, str],
    initials_overrides: dict[str, str],
) -> dict[str, int]:
    """Create developer_firms rows for all canonical firm names.

    Returns {firm_name: firm_id}.
    """
    canonical_names = sorted(set(alias_map.values()))

    firm_ids: dict[str, int] = {}
    for firm_name in canonical_names:
        norm = normalize_firm_name(firm_name)
        initials = _firm_initials(firm_name, initials_overrides)
        row = await session.execute(
            text("""
                INSERT INTO developer_firms (firm_name, firm_name_normalized, firm_initials, updated_at)
                VALUES (:name, :norm, :initials, NOW())
                ON CONFLICT (firm_name_normalized)
                DO UPDATE SET
                    firm_name = EXCLUDED.firm_name,
                    firm_initials = EXCLUDED.firm_initials,
                    updated_at = NOW()
                RETURNING id
            """),
            {"name": firm_name, "norm": norm, "initials": initials},
        )
        fid = row.scalar()
        firm_ids[firm_name] = fid

    await session.commit()
    log.info("developer_firms_populated", count=len(firm_ids))
    return firm_ids


async def map_investments_to_firms(
    session: AsyncSession,
    alias_map: dict[str, str],
    firm_ids: dict[str, int],
) -> int:
    """Update jawnosc_developers.firm_id using alias_map + normalization."""
    rows = await session.execute(
        text("SELECT id, developer_name FROM jawnosc_developers WHERE firm_id IS NULL LIMIT 20000")
    )
    mappings = rows.fetchall()

    updated = 0
    for dev_id, dev_name in mappings:
        norm = normalize_firm_name(dev_name)

        # Try alias map first (longest whole-word match).
        # Use word-boundary regex to prevent "echo" matching "techone" / "czechowicach".
        firm_name: str | None = None
        best_len = 0
        for alias, canonical in alias_map.items():
            if _re.search(r'\b' + _re.escape(alias) + r'\b', norm) and len(alias) > best_len:
                firm_name = canonical
                best_len = len(alias)

        if firm_name and firm_name in firm_ids:
            await session.execute(
                text("UPDATE jawnosc_developers SET firm_id = :fid WHERE id = :id"),
                {"fid": firm_ids[firm_name], "id": dev_id},
            )
            updated += 1

    await session.commit()
    log.info("investments_mapped_to_firms", updated=updated, total=len(mappings))
    return updated


# ── Feed re-probe for freshness ───────────────────────────────────────────────

async def reprobe_stale_warsaw_feeds(
    factory: async_sessionmaker,
    client: DaneGovClient,
    *,
    max_reprobe: int = 500,
) -> dict[str, int]:
    """Re-probe stale Warsaw-candidate feeds using feed-internal freshness.

    Each reprobe uses its own session to avoid asyncpg concurrency conflicts.
    """
    async with factory() as session:
        rows = await session.execute(text("""
            SELECT id, feed_url, developer_name
            FROM jawnosc_developers
            WHERE feed_url IS NOT NULL
              AND sync_status = 'stale'
              AND (
                  developer_name ~* '(warszawa|wola|mokotow|zoliborz|ursynow|wilanow|srodmiescie|
                                       bialoleka|bemowo|bielany|targowek|ursus|wlochy|ochota|wawer|
                                       praga|rembert|wesola|dom.development|atal|robyg|echo|develia|
                                       marvipol|murapol|yareal|matexi|okam|archicom|lokum|victoria|
                                       budimex|spravia|cordia|eiffage|ronson|inpro)'
              )
            ORDER BY id
            LIMIT :lim
        """), {"lim": max_reprobe})
        candidates = rows.fetchall()

    log.info("reprobe_start", candidates=len(candidates))
    counts: dict[str, int] = {"active": 0, "recently_active": 0, "stale": 0, "unknown": 0}
    sem = asyncio.Semaphore(10)

    async def reprobe_one(dev_id: int, feed_url: str) -> None:
        async with sem:
            try:
                xml = await client.get_bytes(feed_url)
                most_recent = _extract_freshness_from_catalog(xml)
                freshness = classify_freshness(most_recent)
            except Exception:
                freshness = "unknown"
                most_recent = None

            counts[freshness] = counts.get(freshness, 0) + 1
            async with factory() as s:
                await s.execute(text("""
                    UPDATE jawnosc_developers
                    SET feed_freshness = :freshness,
                        last_seen_date = :date,
                        sync_status = CASE WHEN :freshness = 'active' THEN 'active' ELSE sync_status END,
                        updated_at = NOW()
                    WHERE id = :id
                """), {"freshness": freshness, "date": most_recent, "id": dev_id})
                await s.commit()

    await asyncio.gather(*[reprobe_one(r[0], r[1]) for r in candidates])
    log.info("reprobe_complete", **counts)
    return counts


# ── Core ingestion ─────────────────────────────────────────────────────────────

async def ingest_developer(
    factory: async_sessionmaker,
    client: DaneGovClient,
    dev_id: int,
    dev_name: str,
    firm_id: int | None,
    feed_url: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch, parse, and upsert one developer's pricing data.

    Returns {ok, error, dwellings_parsed, upserted, status_dist, format}.
    """
    result: dict[str, Any] = {
        "dev_id": dev_id, "dev_name": dev_name,
        "ok": False, "error": None, "dwellings_parsed": 0,
        "upserted": 0, "status_dist": {}, "format": None,
    }

    # 1. Fetch XML catalog
    try:
        xml = await client.get_bytes(feed_url)
    except Exception as exc:
        result["error"] = f"feed_unreachable: {exc}"
        return result

    cat = FeedCatalogParser.parse(xml)
    if not cat.get("latest_url"):
        result["error"] = "no_latest_url"
        return result

    result["format"] = cat["data_format"]

    # Update feed freshness + fetch data file (no DB yet)
    most_recent = _extract_freshness_from_catalog(xml)
    freshness = classify_freshness(most_recent)

    # 2. Fetch latest data file
    try:
        raw = await client.get_bytes(cat["latest_url"])
    except Exception as exc:
        result["error"] = f"data_file_unreachable: {exc}"
        return result

    # 3. Parse
    dwellings, parse_err = parse_feed_file(raw, cat["data_format"] or "csv")
    if parse_err and not dwellings:
        result["error"] = f"parse_error: {parse_err}"
        if not dry_run:
            async with factory() as s:
                await s.execute(text(
                    "UPDATE jawnosc_developers SET sync_status='schema_error', updated_at=NOW() WHERE id=:id"
                ), {"id": dev_id})
                await s.commit()
        return result

    result["dwellings_parsed"] = len(dwellings)
    today = date.today()
    status_dist: dict[str, int] = {}

    if dry_run:
        result["ok"] = True
        for d in dwellings:
            status_dist[d.status] = status_dist.get(d.status, 0) + 1
        result["status_dist"] = status_dist
        return result

    # 4. Upsert into primary_pricing — one session per developer
    async with factory() as session:
        # Update jawnosc_developers metadata first
        await session.execute(text("""
            UPDATE jawnosc_developers SET
                feed_freshness = :freshness, last_seen_date = :date,
                data_format = :fmt, schema_version = :sv,
                sync_status = CASE WHEN :freshness = 'active' THEN 'active' ELSE sync_status END,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "freshness": freshness, "date": most_recent,
            "fmt": cat["data_format"], "sv": cat.get("schema_version"),
            "id": dev_id,
        })

        upserted = 0
        for dw in dwellings:
            district = resolve_warsaw_district(dw.city, dw.street, dw.voivodeship) or dw.district
            ph_entry: dict = {
                "date": str(dw.price_date or today),
                "m2_price": dw.m2_price,
                "total_price": dw.total_price,
                "status": dw.status,
            }

            await session.execute(text("""
                INSERT INTO primary_pricing (
                    dwelling_id, developer_id, firm_id, investment_name,
                    district, city, street, voivodeship,
                    m2_price, total_price, unit_area, unit_type,
                    status, price_history, as_of_date,
                    source_url, source_format, schema_variant
                ) VALUES (
                    :dwelling_id, :dev_id, :firm_id, :inv_name,
                    :district, :city, :street, :voiv,
                    :m2_price, :total_price, :unit_area, :unit_type,
                    :status, CAST(:ph AS jsonb), :as_of_date,
                    :source_url, :source_format, :schema_variant
                )
                ON CONFLICT (dwelling_id, developer_id)
                DO UPDATE SET
                    m2_price      = EXCLUDED.m2_price,
                    total_price   = EXCLUDED.total_price,
                    unit_area     = COALESCE(EXCLUDED.unit_area, primary_pricing.unit_area),
                    status        = EXCLUDED.status,
                    district      = COALESCE(EXCLUDED.district, primary_pricing.district),
                    firm_id       = COALESCE(EXCLUDED.firm_id, primary_pricing.firm_id),
                    as_of_date    = EXCLUDED.as_of_date,
                    price_history = CASE
                        WHEN primary_pricing.m2_price IS DISTINCT FROM EXCLUDED.m2_price
                            OR primary_pricing.status IS DISTINCT FROM EXCLUDED.status
                        THEN primary_pricing.price_history || CAST(:ph AS jsonb)
                        ELSE primary_pricing.price_history
                    END,
                    updated_at    = NOW()
            """), {
                "dwelling_id": dw.dwelling_id, "dev_id": dev_id, "firm_id": firm_id,
                "inv_name": dw.investment_name, "district": district,
                "city": dw.city, "street": dw.street, "voiv": dw.voivodeship,
                "m2_price": dw.m2_price, "total_price": dw.total_price,
                "unit_area": dw.unit_area, "unit_type": dw.unit_type,
                "status": dw.status, "ph": json.dumps([ph_entry]),
                "as_of_date": today, "source_url": cat["latest_url"],
                "source_format": dw.source_format, "schema_variant": dw.schema_variant,
            })
            upserted += 1
            status_dist[dw.status] = status_dist.get(dw.status, 0) + 1

        await session.execute(text("""
            UPDATE jawnosc_developers SET
                active_units_count = :units, last_sync = NOW(),
                sync_status = 'active', updated_at = NOW()
            WHERE id = :id
        """), {"units": len(dwellings), "id": dev_id})

        await session.commit()

    result["ok"] = True
    result["upserted"] = upserted
    result["status_dist"] = status_dist
    return result


# ── Main canary runner ─────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Jawnosc 2B canary ingestion")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--firm", help="Run for a single firm name only")
    parser.add_argument("--skip-reprobe", action="store_true",
                        help="Skip stale feed re-probe step")
    args = parser.parse_args()

    alias_map, initials_overrides = load_aliases()

    db_url = _make_async_url(str(settings.database_url))
    engine = create_async_engine(db_url, echo=False)
    Factory = async_sessionmaker(engine, expire_on_commit=False)

    async with DaneGovClient(requests_per_second=4.0) as client:
        async with Factory() as session:
            # Step 1: Populate developer_firms
            firm_ids = await populate_developer_firms(session, alias_map, initials_overrides)
            await map_investments_to_firms(session, alias_map, firm_ids)

            # Step 2: Re-probe stale Warsaw feeds
            if not args.skip_reprobe:
                reprobe_counts = await reprobe_stale_warsaw_feeds(Factory, client, max_reprobe=400)
                print(f"\nStale re-probe: {reprobe_counts}")

            # Step 3: Build list of target developers
            target_firms = [args.firm] if args.firm else PRIORITY_FIRMS
            firm_name_filter = " OR ".join(
                f"LOWER(jd.developer_name) LIKE '%{f.lower().split()[0]}%'"
                for f in target_firms
            )

            # Find all datasets for priority firms (active + recently_active + stale with feed_url)
            devs_rows = await session.execute(text(f"""
                SELECT jd.id, jd.developer_name, jd.firm_id, jd.feed_url,
                       jd.sync_status, jd.feed_freshness, jd.data_format
                FROM jawnosc_developers jd
                WHERE jd.feed_url IS NOT NULL
                  AND ({firm_name_filter})
                ORDER BY jd.active_units_count DESC, jd.id
            """))
            devs = devs_rows.fetchall()
            print(f"\nFound {len(devs)} datasets matching priority firms")

            # Step 4: Ingest each
            results: list[dict] = []
            sem = asyncio.Semaphore(5)

            async def run_one(row: tuple) -> None:
                dev_id, dev_name, firm_id, feed_url = row[0], row[1], row[2], row[3]
                async with sem:
                    res = await ingest_developer(
                        Factory, client, dev_id, dev_name, firm_id, feed_url,
                        dry_run=args.dry_run
                    )
                    results.append(res)
                    status = "OK" if res["ok"] else "FAIL"
                    units = res["dwellings_parsed"]
                    err = res.get("error") or ""
                    print(f"  [{status}] {dev_name[:55]:55s}  units={units}  fmt={res['format']}  {err[:60]}")

            await asyncio.gather(*[run_one(r) for r in devs])

    # Print summary report
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    total_units = sum(r["dwellings_parsed"] for r in ok)

    print("\n" + "=" * 70)
    print("2B CANARY REPORT")
    print("=" * 70)
    print(f"Datasets attempted: {len(results)}")
    print(f"Successful: {len(ok)}  Failed: {len(fail)}")
    print(f"Total dwellings parsed: {total_units:,}")

    if fail:
        print(f"\nFailed ({len(fail)}):")
        for r in fail:
            print(f"  {r['dev_name'][:55]:55s}  {r.get('error','?')[:60]}")

    # Status distribution
    all_status: dict[str, int] = {}
    for r in ok:
        for k, v in r.get("status_dist", {}).items():
            all_status[k] = all_status.get(k, 0) + v
    print(f"\nStatus distribution: {all_status}")

    print("=" * 70 + "\n")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
