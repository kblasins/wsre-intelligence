"""Warsaw district boundary ingestion from OpenStreetMap.

Fetches 18 dzielnica polygons via Overpass API (admin_level=9 relations
within Warsaw city boundary), assembles MultiPolygon WKT using shapely,
upserts into warsaw_districts, then runs PostGIS spatial join to
populate warsaw_pois.district.

Entry point: run_district_ingestion()
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import structlog
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from app.core.database import AsyncSessionFactory

log = structlog.get_logger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_TIMEOUT = 180

# Warsaw OSM area ID: relation 336075 → area ID = 3600336075
_WARSAW_AREA_ID = 3600336075

# Overpass query: all admin_level=9 boundary relations inside Warsaw
_DISTRICT_QUERY = f"""
[out:json][timeout:120];
area({_WARSAW_AREA_ID})->.warsaw;
(
  relation["admin_level"="9"]["boundary"="administrative"](area.warsaw);
);
out geom;
"""

# Canonical name mapping from OSM name tags → our canonical form
# Keys are lowercased OSM name values
_CANONICAL: dict[str, str] = {
    "śródmieście": "śródmieście",
    "wola": "wola",
    "mokotów": "mokotów",
    "ochota": "ochota",
    "żoliborz": "żoliborz",
    "bielany": "bielany",
    "białołęka": "białołęka",
    "targówek": "targówek",
    "praga-północ": "praga-północ",
    "praga-południe": "praga-południe",
    "rembertów": "rembertów",
    "wesoła": "wesoła",
    "wawer": "wawer",
    "ursynów": "ursynów",
    "wilanów": "wilanów",
    "włochy": "włochy",
    "ursus": "ursus",
    "bemowo": "bemowo",
    # common variants
    "dzielnica śródmieście": "śródmieście",
    "dzielnica wola": "wola",
    "dzielnica mokotów": "mokotów",
    "dzielnica ochota": "ochota",
    "dzielnica żoliborz": "żoliborz",
    "dzielnica bielany": "bielany",
    "dzielnica białołęka": "białołęka",
    "dzielnica targówek": "targówek",
    "dzielnica praga-północ": "praga-północ",
    "dzielnica praga-południe": "praga-południe",
    "dzielnica rembertów": "rembertów",
    "dzielnica wesoła": "wesoła",
    "dzielnica wawer": "wawer",
    "dzielnica ursynów": "ursynów",
    "dzielnica wilanów": "wilanów",
    "dzielnica włochy": "włochy",
    "dzielnica ursus": "ursus",
    "dzielnica bemowo": "bemowo",
}


def _canonical_name(osm_name: str | None) -> str | None:
    if not osm_name:
        return None
    key = osm_name.strip().lower()
    return _CANONICAL.get(key)


def _assemble_multipolygon(members: list[dict]) -> MultiPolygon | None:
    """Assemble a MultiPolygon from Overpass relation members (out geom).

    Members with role 'outer' form outer rings; 'inner' members form holes.
    Uses shapely polygonize to close open linestrings into rings.
    """
    outer_lines = []
    inner_lines = []

    for m in members:
        if m.get("type") != "way":
            continue
        geometry = m.get("geometry", [])
        if not geometry:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geometry]
        if len(coords) < 2:
            continue
        from shapely.geometry import LineString
        line = LineString(coords)
        role = m.get("role", "outer")
        if role == "inner":
            inner_lines.append(line)
        else:
            outer_lines.append(line)

    outer_polys = list(polygonize(outer_lines))
    inner_polys = list(polygonize(inner_lines))

    if not outer_polys:
        return None

    # Subtract inner holes from outer polygons
    result_polys: list[Polygon] = []
    for outer in outer_polys:
        shape = outer
        for inner in inner_polys:
            if shape.contains(inner):
                shape = shape.difference(inner)
        result_polys.append(shape)

    merged = unary_union(result_polys)

    if merged.geom_type == "Polygon":
        return MultiPolygon([merged])
    elif merged.geom_type == "MultiPolygon":
        return merged
    else:
        # GeometryCollection or other — extract polygons
        polys = [g for g in merged.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return None
        return MultiPolygon(polys) if len(polys) > 1 else MultiPolygon([polys[0]])


async def _fetch_districts(client: httpx.AsyncClient) -> list[dict]:
    log.info("osm_districts_fetch_start")
    try:
        resp = await client.post(
            _OVERPASS_URL,
            data={"data": _DISTRICT_QUERY},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        elements = data.get("elements", [])
        log.info("osm_districts_fetch_done", relations=len(elements))
        return elements
    except Exception as exc:
        log.error("osm_districts_fetch_error", error=str(exc)[:300])
        return []


async def _upsert_districts(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    from sqlalchemy import text

    inserted = 0
    async with AsyncSessionFactory() as session:
        for r in rows:
            await session.execute(text("""
                INSERT INTO warsaw_districts
                    (osm_relation_id, name_canonical, name_osm, geometry)
                VALUES
                    (:osm_id, :name_canonical, :name_osm,
                     ST_Multi(ST_SetSRID(ST_GeomFromText(:wkt), 4326)))
                ON CONFLICT (osm_relation_id) DO UPDATE SET
                    name_canonical = EXCLUDED.name_canonical,
                    name_osm       = EXCLUDED.name_osm,
                    geometry       = EXCLUDED.geometry,
                    updated_at     = NOW()
            """), r)
            inserted += 1
        await session.commit()

    return inserted


async def _run_spatial_join() -> int:
    """UPDATE warsaw_pois.district via PostGIS ST_Within against warsaw_districts."""
    from sqlalchemy import text

    async with AsyncSessionFactory() as session:
        result = await session.execute(text("""
            UPDATE warsaw_pois p
            SET district = wd.name_canonical
            FROM warsaw_districts wd
            WHERE ST_Within(p.coordinates, wd.geometry)
        """))
        updated = result.rowcount
        await session.commit()

    return updated


async def run_district_ingestion() -> dict[str, Any]:
    """Fetch Warsaw district polygons and resolve POI districts.

    Returns summary dict with district counts and POI coverage.
    """
    headers = {
        "User-Agent": "WSRE-Intelligence/1.0 Warsaw RE research tool (contact: internal)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=_TIMEOUT) as client:
        elements = await _fetch_districts(client)

    if not elements:
        log.error("osm_districts_no_elements")
        return {"districts_loaded": 0, "pois_resolved": 0}

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []

    for el in elements:
        if el.get("type") != "relation":
            continue

        osm_id = el["id"]
        tags = el.get("tags") or {}
        osm_name = tags.get("name")
        name_canonical = _canonical_name(osm_name)

        if not name_canonical:
            skipped.append(f"{osm_id}:{osm_name}")
            log.warning("osm_district_unknown_name", osm_id=osm_id, name=osm_name)
            continue

        members = el.get("members") or []
        mp = _assemble_multipolygon(members)
        if mp is None or mp.is_empty:
            log.warning("osm_district_empty_geometry", name=name_canonical, osm_id=osm_id)
            continue

        from shapely import wkt as shapely_wkt
        wkt_str = shapely_wkt.dumps(mp, rounding_precision=7)

        rows.append({
            "osm_id": osm_id,
            "name_canonical": name_canonical,
            "name_osm": osm_name,
            "wkt": wkt_str,
        })
        log.info("osm_district_parsed", name=name_canonical, members=len(members))

    log.info("osm_districts_parsed", count=len(rows), skipped=len(skipped))

    districts_loaded = await _upsert_districts(rows)
    log.info("osm_districts_upserted", count=districts_loaded)

    pois_resolved = await _run_spatial_join()
    log.info("osm_districts_spatial_join_done", pois_resolved=pois_resolved)

    return {
        "districts_loaded": districts_loaded,
        "pois_resolved": pois_resolved,
        "skipped": skipped,
    }


if __name__ == "__main__":
    import asyncio as _asyncio
    from app.core.logging import configure_logging
    configure_logging()
    result = _asyncio.run(run_district_ingestion())
    print("\n=== Warsaw District Ingestion Results ===")
    print(f"  Districts loaded : {result['districts_loaded']}")
    print(f"  POIs resolved    : {result['pois_resolved']}")
    if result.get("skipped"):
        print(f"  Skipped          : {result['skipped']}")
