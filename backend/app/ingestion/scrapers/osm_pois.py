"""Warsaw POI ingestion from OpenStreetMap via Overpass API.

Fetches 6 POI categories for Warsaw and upserts into warsaw_pois table.
Polite rate-limiting: 2 seconds between Overpass queries.

Categories:
  school          — amenity=school + amenity=kindergarten
  healthcare      — amenity=hospital/clinic/doctors + healthcare=*
  park            — leisure=park
  metro_station   — railway=station + station=subway
  tram_stop       — railway=tram_stop
  rail_station    — railway=station (non-subway)

Entry point: run_osm_poi_ingestion()
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.core.database import AsyncSessionFactory

log = structlog.get_logger(__name__)

# Warsaw bounding box: south, west, north, east
_BBOX = "52.0975,20.8516,52.3681,21.2716"

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_REQUEST_DELAY = 2.5  # seconds between queries — polite
_TIMEOUT = 120

# ── Overpass queries ──────────────────────────────────────────────────────────

_QUERIES: list[tuple[str, str]] = [
    ("school", f"""
[out:json][timeout:120];
(
  node["amenity"="school"]({_BBOX});
  way["amenity"="school"]({_BBOX});
  node["amenity"="kindergarten"]({_BBOX});
  way["amenity"="kindergarten"]({_BBOX});
);
out center;
"""),
    ("healthcare", f"""
[out:json][timeout:120];
(
  node["amenity"~"^(hospital|clinic|doctors)$"]({_BBOX});
  way["amenity"~"^(hospital|clinic|doctors)$"]({_BBOX});
  node["healthcare"]({_BBOX});
  way["healthcare"]({_BBOX});
);
out center;
"""),
    ("park", f"""
[out:json][timeout:120];
(
  way["leisure"="park"]({_BBOX});
  relation["leisure"="park"]({_BBOX});
  node["leisure"="park"]({_BBOX});
);
out center;
"""),
    ("metro_station", f"""
[out:json][timeout:120];
(
  node["railway"="station"]["station"="subway"]({_BBOX});
  node["railway"="halt"]["station"="subway"]({_BBOX});
);
out;
"""),
    ("tram_stop", f"""
[out:json][timeout:120];
(
  node["railway"="tram_stop"]({_BBOX});
);
out;
"""),
    ("rail_station", f"""
[out:json][timeout:120];
(
  node["railway"="station"]["station"!="subway"]({_BBOX});
);
out;
"""),
]

# ── Warsaw dzielnica canonical names ──────────────────────────────────────────

_DZIELNICE = {
    "śródmieście", "wola", "mokotów", "ochota", "żoliborz", "bielany",
    "białołęka", "targówek", "praga-północ", "praga-południe",
    "rembertów", "wesoła", "wawer", "ursynów", "wilanów", "włochy",
    "ursus", "bemowo",
}

# Normalisation map for OSM tag variants → canonical dzielnica
_DISTRICT_ALIASES: dict[str, str] = {
    "srodmiescie": "śródmieście",
    "sredmiescie": "śródmieście",
    "mokotow": "mokotów",
    "zoliborz": "żoliborz",
    "bialoleka": "białołęka",
    "bialołęka": "białołęka",
    "targowek": "targówek",
    "praga polnoc": "praga-północ",
    "praga-polnoc": "praga-północ",
    "praga północ": "praga-północ",
    "praga poludnie": "praga-południe",
    "praga-poludnie": "praga-południe",
    "praga południe": "praga-południe",
    "rembertow": "rembertów",
    "wesola": "wesoła",
    "ursynow": "ursynów",
    "wilanow": "wilanów",
    "wlochy": "włochy",
}


def _normalize_district(raw: str | None) -> str | None:
    """Normalise an OSM tag value to a canonical dzielnica name, or None."""
    if not raw:
        return None
    s = raw.strip().lower()
    # Direct match
    if s in _DZIELNICE:
        return s
    # Alias match
    if s in _DISTRICT_ALIASES:
        return _DISTRICT_ALIASES[s]
    # Partial match — check if a dzielnica name is contained
    for d in _DZIELNICE:
        if d in s:
            return d
    return None


def _extract_district(tags: dict[str, str]) -> str | None:
    """Extract dzielnica from OSM tag candidates, best-match first."""
    for key in ("addr:suburb", "addr:city_district", "addr:quarter", "addr:district", "is_in:suburb"):
        if val := tags.get(key):
            if norm := _normalize_district(val):
                return norm
    return None


# ── Category / subcategory mapping ───────────────────────────────────────────

def _school_subcategory(tags: dict[str, str]) -> str:
    amenity = tags.get("amenity", "")
    if amenity == "kindergarten":
        return "kindergarten"
    school_type = tags.get("school:type") or tags.get("isced:level") or ""
    name = (tags.get("name") or "").lower()
    if "podstawow" in name or "primary" in name or school_type in ("1", "primary"):
        return "primary_school"
    if "liceum" in name or "technikum" in name or "secondary" in name or school_type in ("2", "3"):
        return "secondary_school"
    return "school"


def _healthcare_subcategory(tags: dict[str, str]) -> str:
    amenity = tags.get("amenity", "")
    hc = tags.get("healthcare", "")
    if amenity == "hospital" or hc == "hospital":
        return "hospital"
    if amenity == "clinic" or hc == "clinic":
        return "clinic"
    if amenity == "doctors" or hc in ("doctor", "general_practitioner"):
        return "doctors"
    if hc == "pharmacy" or tags.get("amenity") == "pharmacy":
        return "pharmacy"
    return hc or amenity or "healthcare"


def _park_subcategory(tags: dict[str, str]) -> str:
    name = (tags.get("name") or "").lower()
    area = tags.get("area") or ""
    if "park narodow" in name or "rezerwat" in name:
        return "nature_reserve"
    if "las" in name or "forest" in name:
        return "urban_forest"
    return "urban_park"


def _rail_subcategory(tags: dict[str, str]) -> str:
    return tags.get("station") or tags.get("railway") or "rail"


# ── Address builder ───────────────────────────────────────────────────────────

def _build_address(tags: dict[str, str]) -> str | None:
    parts = []
    if street := tags.get("addr:street"):
        parts.append(street)
        if num := tags.get("addr:housenumber"):
            parts[-1] += f" {num}"
    if city := tags.get("addr:city"):
        parts.append(city)
    return ", ".join(parts) or None


# ── Name extraction ───────────────────────────────────────────────────────────

def _extract_names(tags: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    """Returns (name, name_pl, name_en)."""
    name = tags.get("name")
    name_pl = tags.get("name:pl") or tags.get("official_name")
    name_en = tags.get("name:en")
    return name, name_pl, name_en


# ── Coordinate extraction ─────────────────────────────────────────────────────

def _coords(element: dict) -> tuple[float, float] | None:
    """Extract (lat, lon) from a node, way+center, or relation+center."""
    if element.get("type") == "node":
        lat = element.get("lat")
        lon = element.get("lon")
    else:
        center = element.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


# ── Parse Overpass elements ───────────────────────────────────────────────────

def _parse_elements(
    elements: list[dict],
    category: str,
) -> list[dict[str, Any]]:
    """Convert raw Overpass elements to row dicts for warsaw_pois."""
    rows: list[dict[str, Any]] = []

    for el in elements:
        tags = el.get("tags") or {}
        coords = _coords(el)
        if not coords:
            continue
        lat, lon = coords

        osm_type = el.get("type", "node")
        osm_id = el.get("id", 0)

        name, name_pl, name_en = _extract_names(tags)
        address = _build_address(tags)
        district = _extract_district(tags)

        # Subcategory
        if category == "school":
            subcat = _school_subcategory(tags)
        elif category == "healthcare":
            subcat = _healthcare_subcategory(tags)
        elif category == "park":
            subcat = _park_subcategory(tags)
        elif category in ("metro_station", "tram_stop"):
            subcat = "metro" if category == "metro_station" else "tram"
        else:
            subcat = _rail_subcategory(tags)

        rows.append({
            "osm_id": osm_id,
            "osm_type": osm_type,
            "category": category,
            "subcategory": subcat,
            "name": name,
            "name_pl": name_pl,
            "name_en": name_en,
            "address": address,
            "district": district,
            "lat": lat,
            "lon": lon,
            "tags": tags,
        })

    return rows


# ── Overpass fetch ────────────────────────────────────────────────────────────

async def _fetch_overpass(client: httpx.AsyncClient, category: str, query: str) -> list[dict]:
    """POST a single Overpass query and return the parsed elements list."""
    log.info("osm_poi_fetch_start", category=category)
    try:
        resp = await client.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        elements = data.get("elements", [])
        log.info("osm_poi_fetch_done", category=category, elements=len(elements))
        return elements
    except httpx.HTTPStatusError as exc:
        log.error("osm_poi_http_error", category=category, status=exc.response.status_code)
        return []
    except Exception as exc:
        log.error("osm_poi_fetch_error", category=category, error=str(exc)[:200])
        return []


# ── Upsert ────────────────────────────────────────────────────────────────────

async def _upsert_rows(rows: list[dict[str, Any]]) -> int:
    """Upsert parsed POI rows into warsaw_pois. Returns count inserted/updated."""
    if not rows:
        return 0

    from sqlalchemy import text

    now = datetime.now(UTC)
    inserted = 0

    async with AsyncSessionFactory() as session:
        for r in rows:
            await session.execute(text("""
                INSERT INTO warsaw_pois
                    (osm_id, osm_type, category, subcategory,
                     name, name_pl, name_en, address, district,
                     coordinates, tags, created_at, updated_at)
                VALUES
                    (:osm_id, :osm_type, :category, :subcategory,
                     :name, :name_pl, :name_en, :address, :district,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                     CAST(:tags AS jsonb), :now, :now)
                ON CONFLICT (osm_id, osm_type) DO UPDATE SET
                    category    = EXCLUDED.category,
                    subcategory = EXCLUDED.subcategory,
                    name        = EXCLUDED.name,
                    name_pl     = EXCLUDED.name_pl,
                    name_en     = EXCLUDED.name_en,
                    address     = EXCLUDED.address,
                    district    = EXCLUDED.district,
                    coordinates = EXCLUDED.coordinates,
                    tags        = EXCLUDED.tags,
                    updated_at  = EXCLUDED.updated_at
            """), {
                "osm_id": r["osm_id"],
                "osm_type": r["osm_type"],
                "category": r["category"],
                "subcategory": r["subcategory"],
                "name": r["name"],
                "name_pl": r["name_pl"],
                "name_en": r["name_en"],
                "address": r["address"],
                "district": r["district"],
                "lon": r["lon"],
                "lat": r["lat"],
                "tags": json.dumps(r["tags"]),
                "now": now,
            })
            inserted += 1

        await session.commit()

    return inserted


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_osm_poi_ingestion() -> dict[str, int]:
    """Fetch all 6 POI categories from Overpass and upsert into warsaw_pois.

    Returns a dict of {category: count_upserted}.
    """
    headers = {
        "User-Agent": "WSRE-Intelligence/1.0 Warsaw RE research tool (contact: internal)",
        "Accept": "application/json",
    }

    results: dict[str, int] = {}

    async with httpx.AsyncClient(headers=headers, timeout=_TIMEOUT) as client:
        for i, (category, query) in enumerate(_QUERIES):
            if i > 0:
                await asyncio.sleep(_REQUEST_DELAY)

            elements = await _fetch_overpass(client, category, query)
            if not elements:
                log.warning("osm_poi_no_elements", category=category)
                results[category] = 0
                continue

            rows = _parse_elements(elements, category)
            count = await _upsert_rows(rows)
            results[category] = count
            log.info("osm_poi_upserted", category=category, count=count)

    total = sum(results.values())
    log.info("osm_poi_ingestion_complete", total=total, by_category=results)
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio as _asyncio
    from app.core.logging import configure_logging
    configure_logging()
    counts = _asyncio.run(run_osm_poi_ingestion())
    print("\n=== OSM POI Ingestion Results ===")
    for cat, n in counts.items():
        print(f"  {cat:<20} {n:>6}")
    print(f"  {'TOTAL':<20} {sum(counts.values()):>6}")
