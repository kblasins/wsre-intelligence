"""Overpass API POI scraper — weekly refresh for Riyadh metro area.

Queries the OpenStreetMap Overpass API for POIs in the Riyadh metropolitan
bounding box, then upserts into the pois table using (source, osm_id, osm_type)
as the natural key. Re-confirmed records have last_seen_at updated. POIs that
disappeared from the API response are NOT deleted — they are left with a stale
last_seen_at so consumers can filter by recency.

Run weekly: Sunday 02:00 UTC.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.database import AsyncSessionFactory
from app.models.spatial import POI

log = structlog.get_logger(__name__)

SOURCE = "osm_overpass"

# Riyadh metropolitan bounding box (south, west, north, east)
RIYADH_BBOX = (24.35, 46.35, 25.15, 47.15)

# Overpass API endpoint — public instance, rate-limited
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Maximum elements to request per category query (circuit-breaker)
MAX_ELEMENTS_PER_QUERY = 10_000

# Categories to fetch. Each entry maps to an Overpass tag filter.
# Format: (category, subcategory, overpass_filter)
#
# Taxonomy: 8 top-level categories, 40 subcategories.
# Queries ported from riyadh-intel-v3-poi35.html (previous project) with
# subcategory_group metadata derived client-side via SUBCATEGORY_GROUP lookup.
CATEGORIES: list[tuple[str, str, str]] = [
    # ── Transportation ────────────────────────────────────────────────────
    ("transportation", "fuel",       'amenity="fuel"'),
    # structured/named parking only — bare amenity=parking has tens of thousands of nodes
    ("transportation", "parking",    'amenity="parking"[parking~"multi-storey|underground|surface"][name~"."]'),
    ("transportation", "bus",        'amenity~"bus_station|bus_stop"'),
    ("transportation", "car_dealer", 'shop="car"[name~"."]'),

    # ── Industrial ────────────────────────────────────────────────────────
    ("industrial", "warehouse",   'building~"warehouse|industrial|manufacture"'),
    ("industrial", "data_centre", 'building~"data_cent"'),

    # ── Commercial ────────────────────────────────────────────────────────
    ("commercial", "mall",        'shop~"mall|department_store"'),
    ("commercial", "supermarket", 'shop~"supermarket|hypermarket"'),
    ("commercial", "hotel",       'tourism="hotel"'),
    # named restaurants only — unnamed nodes are mostly fast-food counters/stalls
    ("commercial", "restaurant",  'amenity="restaurant"[name~"."]'),
    ("commercial", "cafe",        'amenity~"cafe|coffee_shop"'),
    ("commercial", "office_bld",  'building="office"'),
    ("commercial", "cowork",      'amenity="coworking_space"'),
    ("commercial", "bank",        'amenity="bank"'),
    ("commercial", "atm",         'amenity="atm"'),

    # ── Amenity — health ──────────────────────────────────────────────────
    ("amenity", "hospital",  'amenity="hospital"'),
    ("amenity", "clinic",    'amenity~"clinic|doctors"'),
    ("amenity", "pharmacy",  'amenity="pharmacy"'),
    ("amenity", "dental",    'amenity="dentist"'),

    # ── Amenity — recreation ──────────────────────────────────────────────
    ("amenity", "gym",     'leisure~"fitness_centre|gym"'),
    ("amenity", "pool",    'leisure="swimming_pool"'),
    # named parks only — unnamed leisure=park tags are common on scrubland/unmanaged areas
    ("amenity", "park",    'leisure~"park|garden"[name~"."]'),
    ("amenity", "stadium", 'leisure~"stadium|sports_centre|sports_hall"'),

    # ── Amenity — culture / religion ──────────────────────────────────────
    # named mosques only — Riyadh has thousands of unnamed prayer rooms tagged as place_of_worship
    ("amenity", "mosque",   'amenity="place_of_worship"[religion="muslim"][name~"."]'),
    ("amenity", "cinema",   'amenity="cinema"'),
    ("amenity", "theatre",  'amenity~"theatre|events_venue|conference_centre"'),
    ("amenity", "museum",   'tourism~"museum|gallery"'),
    ("amenity", "library",  'amenity="library"'),

    # ── Education ─────────────────────────────────────────────────────────
    ("education", "nursery",     'amenity~"kindergarten|childcare"'),
    ("education", "school",      'amenity="school"[name~"."]'),
    # intl_school overlaps with school — deduped on upsert by osm_id
    ("education", "intl_school", 'amenity="school"[name~"International|American|British|French|German|Japanese"]'),
    ("education", "university",  'amenity~"university|college"'),

    # ── Government ────────────────────────────────────────────────────────
    ("government", "govt",    'amenity="townhall"'),
    ("government", "modon",   'operator="MODON"'),
    ("government", "police",  'amenity="police"'),
    ("government", "fire",    'amenity="fire_station"'),
    ("government", "post",    'amenity="post_office"'),
    ("government", "embassy", 'amenity~"embassy|consulate"'),

    # ── Infrastructure ────────────────────────────────────────────────────
    ("infrastructure", "power_substation", 'power="substation"'),
    ("infrastructure", "water_tower",      'man_made="water_tower"'),
]

# Client-side subcategory group lookup for the amenity tree toggle.
# Keys are subcategory values; values are one of: health, recreation, culture_religion.
# Non-amenity subcategories are not listed here (they have no group).
SUBCATEGORY_GROUP: dict[str, str] = {
    # health
    "hospital":  "health",
    "clinic":    "health",
    "pharmacy":  "health",
    "dental":    "health",
    # recreation
    "gym":     "recreation",
    "pool":    "recreation",
    "park":    "recreation",
    "stadium": "recreation",
    # culture / religion
    "mosque":   "culture_religion",
    "cinema":   "culture_religion",
    "theatre":  "culture_religion",
    "museum":   "culture_religion",
    "library":  "culture_religion",
}


def _build_overpass_query(category: str, subcategory: str, tag_filter: str) -> str:
    """Build an Overpass QL query for the Riyadh bbox."""
    s, w, n, e = RIYADH_BBOX
    bbox = f"{s},{w},{n},{e}"
    return (
        f"[out:json][timeout:120];\n"
        f"(\n"
        f"  node[{tag_filter}]({bbox});\n"
        f"  way[{tag_filter}]({bbox});\n"
        f"  relation[{tag_filter}]({bbox});\n"
        f");\n"
        f"out center {MAX_ELEMENTS_PER_QUERY};\n"
    )


def _parse_int(v: str | None) -> int | None:
    """Parse an OSM tag value to int, returning None on failure."""
    if not v:
        return None
    try:
        return int(v.strip().split(".")[0])
    except (ValueError, AttributeError):
        return None


def _parse_float(v: str | None) -> float | None:
    """Parse an OSM height tag (may include 'm' suffix) to float."""
    if not v:
        return None
    import re
    m = re.search(r"[\d.]+", v)
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None


def _extract_center(element: dict[str, Any]) -> tuple[float, float] | None:
    """Return (lon, lat) from an Overpass element, or None if not extractable."""
    typ = element.get("type")
    if typ == "node":
        lat = element.get("lat")
        lon = element.get("lon")
    elif typ in ("way", "relation"):
        center = element.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")
    else:
        return None
    if lat is None or lon is None:
        return None
    return float(lon), float(lat)


def _extract_names(tags: dict[str, str]) -> tuple[str | None, str | None]:
    """Extract English and Arabic names from OSM tags."""
    name_en = tags.get("name:en") or tags.get("name") or None
    name_ar = tags.get("name:ar") or None
    # Prefer Arabic name as primary if name is Arabic script
    if name_en and name_ar is None and any("\u0600" <= c <= "\u06ff" for c in name_en):
        name_ar = name_en
        name_en = None
    return name_en, name_ar


async def _fetch_category(
    client: httpx.AsyncClient,
    category: str,
    subcategory: str,
    tag_filter: str,
) -> list[dict[str, Any]]:
    """Fetch all OSM elements for one category. Returns list of parsed records."""
    query = _build_overpass_query(category, subcategory, tag_filter)
    log.debug("overpass_query_start", category=category, subcategory=subcategory)

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=5, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TransportError)),
        reraise=True,
    ):
        with attempt:
            resp = await client.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=90,
            )
            resp.raise_for_status()
            payload = resp.json()

    elements = payload.get("elements", [])
    log.info(
        "overpass_query_done",
        category=category,
        subcategory=subcategory,
        count=len(elements),
    )

    records: list[dict[str, Any]] = []
    for el in elements:
        center = _extract_center(el)
        if center is None:
            continue
        lon, lat = center
        tags = el.get("tags", {})
        name_en, name_ar = _extract_names(tags)
        records.append(
            {
                "osm_id": el.get("id"),
                "osm_type": el.get("type"),
                "category": category,
                "subcategory": subcategory,
                "name_en": name_en,
                "name_ar": name_ar,
                # WKT point — GeoAlchemy2 accepts WKT strings on insert
                "location_wkt": f"SRID=4326;POINT({lon} {lat})",
                "address": tags.get("addr:full") or tags.get("addr:street"),
                "tags": tags,
                "source": SOURCE,
                "operator": tags.get("operator") or tags.get("operator:en"),
                "brand": tags.get("brand") or tags.get("brand:en"),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website"),
                "opening_hours": tags.get("opening_hours"),
                "building_levels": _parse_int(tags.get("building:levels")),
                "height_m": _parse_float(tags.get("height")),
                "capacity": _parse_int(tags.get("capacity")),
            }
        )
    return records


async def run_overpass_refresh() -> None:
    """Main entry point — fetch all categories, upsert into pois table."""
    now = datetime.now(UTC)
    log.info("overpass_refresh_start", categories=len(CATEGORIES))

    all_records: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "WhiteStarHub/1.0 (research; contact@whitestar.sa)"},
        follow_redirects=True,
    ) as client:
        for i, (category, subcategory, tag_filter) in enumerate(CATEGORIES):
            if i > 0:
                await asyncio.sleep(3)  # polite delay between queries
            try:
                records = await _fetch_category(client, category, subcategory, tag_filter)
                all_records.extend(records)
            except Exception:
                log.exception(
                    "overpass_category_failed",
                    category=category,
                    subcategory=subcategory,
                )
                # Continue — partial refresh is better than no refresh

    if not all_records:
        log.warning("overpass_refresh_no_records")
        return

    # Log per-category counts for the post-refresh report
    counts_by_cat: dict[str, dict[str, int]] = {}
    for r in all_records:
        counts_by_cat.setdefault(r["category"], {}).setdefault(r["subcategory"], 0)
        counts_by_cat[r["category"]][r["subcategory"]] += 1
    for cat, subs in sorted(counts_by_cat.items()):
        log.info("overpass_category_count", category=cat, subcategory_counts=subs, total=sum(subs.values()))

    log.info("overpass_refresh_upserting", total=len(all_records))

    inserted = 0
    updated = 0

    async with AsyncSessionFactory() as session:
        for record in all_records:
            wkt = record.pop("location_wkt")
            # Build the upsert — ON CONFLICT on natural key
            stmt = (
                pg_insert(POI)
                .values(
                    osm_id=record["osm_id"],
                    osm_type=record["osm_type"],
                    category=record["category"],
                    subcategory=record["subcategory"],
                    name_en=record["name_en"],
                    name_ar=record["name_ar"],
                    location=text(f"ST_GeomFromEWKT('{wkt}')"),
                    address=record["address"],
                    tags=record["tags"],
                    source=SOURCE,
                    first_seen_at=now,
                    last_seen_at=now,
                    operator=record["operator"],
                    brand=record["brand"],
                    phone=record["phone"],
                    website=record["website"],
                    opening_hours=record["opening_hours"],
                    building_levels=record["building_levels"],
                    height_m=record["height_m"],
                    capacity=record["capacity"],
                )
                .on_conflict_do_update(
                    constraint="uq_poi_source_osm",
                    set_={
                        "category": record["category"],
                        "subcategory": record["subcategory"],
                        "name_en": record["name_en"],
                        "name_ar": record["name_ar"],
                        "location": text(f"ST_GeomFromEWKT('{wkt}')"),
                        "address": record["address"],
                        "tags": record["tags"],
                        "last_seen_at": now,
                        "operator": record["operator"],
                        "brand": record["brand"],
                        "phone": record["phone"],
                        "website": record["website"],
                        "opening_hours": record["opening_hours"],
                        "building_levels": record["building_levels"],
                        "height_m": record["height_m"],
                        "capacity": record["capacity"],
                    },
                )
            )
            result = await session.execute(stmt)
            # rowcount == 1 for insert, 0 for update (postgres returns 0 for no-op updates)
            if result.rowcount == 1:
                inserted += 1
            else:
                updated += 1

        await session.execute(text("""
            UPDATE pois p
            SET district_id = d.id
            FROM districts d
            WHERE p.district_id IS NULL
              AND ST_Within(p.location, d.polygon)
              AND d.polygon IS NOT NULL
        """))

        await session.commit()

    log.info(
        "overpass_refresh_done",
        inserted=inserted,
        updated=updated,
        total=len(all_records),
    )
