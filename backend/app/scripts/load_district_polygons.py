"""Load district polygons from a GeoJSON file into the districts table.

Source: homaily/Saudi-Arabia-Regions-Cities-and-Districts (GitHub)
File:   districts/riyadh.geojson  (or the merged districts.geojson)

Usage:
    cd backend
    python -m app.scripts.load_district_polygons /path/to/riyadh_districts.geojson

The script is idempotent — existing rows are updated (upserted) by name_ar.
Skips features with no geometry.

Expected GeoJSON feature properties (any subset is fine):
  name_ar   Arabic name (used as natural key)
  name_en   English name (optional)
  name      Fallback name if name_en absent
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text

from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging

log = structlog.get_logger(__name__)


def _to_multipolygon_wkt(geometry: dict[str, Any]) -> str | None:
    """Convert a GeoJSON geometry to a MULTIPOLYGON WKT string.

    Accepts Polygon or MultiPolygon. Returns None for unsupported types.
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = []
            for ring in poly:
                pts = ", ".join(f"{lon} {lat}" for lon, lat in ring)
                rings.append(f"({pts})")
            polys.append(f"({', '.join(rings)})")
        return f"MULTIPOLYGON({', '.join(polys)})"

    elif gtype == "Polygon":
        rings = []
        for ring in coords:
            pts = ", ".join(f"{lon} {lat}" for lon, lat in ring)
            rings.append(f"({pts})")
        return f"MULTIPOLYGON(({', '.join(rings)}))"

    return None


def _extract_props(props: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Return (name_ar, name_en, district_code) from feature properties."""
    name_ar = (
        props.get("name_ar")
        or props.get("NAME_AR")
        or props.get("arName")
        or ""
    ).strip()

    name_en = (
        props.get("name_en")
        or props.get("NAME_EN")
        or props.get("enName")
        or props.get("name")
        or props.get("NAME")
        or None
    )
    if name_en:
        name_en = name_en.strip() or None

    district_code = (
        props.get("district_code")
        or props.get("code")
        or props.get("id")
        or None
    )
    if district_code is not None:
        district_code = str(district_code).strip() or None

    return name_ar, name_en, district_code


async def load_polygons(geojson_path: Path) -> None:
    configure_logging()

    raw = geojson_path.read_text(encoding="utf-8")
    fc = json.loads(raw)

    features = fc.get("features", [])
    log.info("geojson_loaded", path=str(geojson_path), feature_count=len(features))

    inserted = 0
    updated = 0
    skipped = 0

    # Geometry variants to try in order — handles winding/validity edge cases
    _INSERT_SQL = text("""
        INSERT INTO districts
            (name_en, name_ar, city, district_code, polygon, source, created_at, updated_at)
        VALUES
            (:name_en, :name_ar, 'Riyadh', :district_code,
             ST_MakeValid(ST_GeomFromEWKT(:wkt)),
             'homaily_geojson', NOW(), NOW())
        ON CONFLICT DO NOTHING
        RETURNING id
    """)
    _UPDATE_SQL = text("""
        UPDATE districts
        SET polygon = ST_MakeValid(ST_GeomFromEWKT(:wkt)),
            district_code = COALESCE(:district_code, district_code),
            updated_at = NOW()
        WHERE (name_ar = :name_ar AND :name_ar IS NOT NULL)
           OR (name_en = :name_en AND name_ar IS NULL)
        RETURNING id
    """)

    async with AsyncSessionFactory() as session:
        for feat in features:
            geometry = feat.get("geometry")
            props = feat.get("properties") or {}

            if not geometry:
                skipped += 1
                continue

            wkt = _to_multipolygon_wkt(geometry)
            if wkt is None:
                log.debug("unsupported_geometry_type", geom_type=geometry.get("type"))
                skipped += 1
                continue

            name_ar, name_en, district_code = _extract_props(props)

            if not name_ar and not name_en:
                log.debug("no_name_skipped", props=props)
                skipped += 1
                continue

            natural_key = name_ar or name_en
            params = {
                "name_en": name_en or natural_key,
                "name_ar": name_ar or None,
                "district_code": district_code,
                "wkt": f"SRID=4326;{wkt}",
            }

            # Commit each feature independently so one bad polygon doesn't abort the batch
            try:
                result = await session.execute(_INSERT_SQL, params)
                row = result.first()
                if row:
                    inserted += 1
                else:
                    upd = await session.execute(_UPDATE_SQL, params)
                    if upd.first():
                        updated += 1
                    else:
                        skipped += 1
                await session.commit()
            except Exception as exc:
                await session.rollback()
                log.debug(
                    "polygon_skipped_invalid",
                    name=natural_key,
                    error=str(exc)[:120],
                )
                skipped += 1

    print(
        f"Done — {inserted} inserted, {updated} updated, {skipped} skipped "
        f"(no geometry or name)"
    )
    log.info(
        "district_polygons_loaded",
        inserted=inserted,
        updated=updated,
        skipped=skipped,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.scripts.load_district_polygons <path/to/districts.geojson>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    asyncio.run(load_polygons(path))
