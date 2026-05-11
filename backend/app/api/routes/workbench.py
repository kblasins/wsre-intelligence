"""Workbench API — plot evaluation and POI map layer endpoints.

Endpoints:
  GET /api/workbench/plot/{plot_id}  — full 9-section plot evaluation JSON
  GET /api/workbench/pois            — GeoJSON FeatureCollection of Warsaw POIs
"""
from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import current_active_user
from app.core.database import get_db_session
from app.models.auth import User
from app.services.plot_evaluation import build_plot_evaluation

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/workbench", tags=["workbench"])

# Default subcategory filters per category (exclude noisy entries)
_DEFAULT_EXCLUDE_SUBCAT: dict[str, set[str]] = {}

# Valid category values
_VALID_CATEGORIES = frozenset({
    "school", "healthcare", "park", "metro_station", "tram_stop", "rail_station",
})


@router.get("/pois")
async def get_pois(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[User, Depends(current_active_user)],
    categories: str = Query(
        default="metro_station,tram_stop,school,healthcare,park",
        description="Comma-separated category list",
    ),
    district: str | None = Query(default=None, description="Filter by dzielnica name"),
    limit: int = Query(default=5000, ge=1, le=20000),
) -> dict[str, Any]:
    """Return a GeoJSON FeatureCollection of Warsaw POIs.

    categories: comma-separated values from
        school, healthcare, park, metro_station, tram_stop, rail_station
    district: optional canonical dzielnica name filter
    limit: max features returned (default 5000, max 20000)
    """
    requested = {c.strip() for c in categories.split(",") if c.strip()}
    invalid = requested - _VALID_CATEGORIES
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown categories: {sorted(invalid)}")

    where_parts = ["category = ANY(:cats)"]
    params: dict[str, Any] = {"cats": list(requested), "limit": limit}

    if district:
        where_parts.append("district = :district")
        params["district"] = district.strip().lower()

    where_sql = " AND ".join(where_parts)

    rows = await session.execute(text(f"""
        SELECT
            id,
            osm_id,
            osm_type,
            category,
            subcategory,
            name,
            name_pl,
            name_en,
            address,
            district,
            ST_X(coordinates::geometry) AS lon,
            ST_Y(coordinates::geometry) AS lat
        FROM warsaw_pois
        WHERE {where_sql}
        ORDER BY id
        LIMIT :limit
    """), params)

    features = []
    for r in rows.mappings():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(r["lon"]), float(r["lat"])],
            },
            "properties": {
                "id": r["id"],
                "osm_id": r["osm_id"],
                "osm_type": r["osm_type"],
                "category": r["category"],
                "subcategory": r["subcategory"],
                "name": r["name"],
                "name_pl": r["name_pl"],
                "name_en": r["name_en"],
                "address": r["address"],
                "district": r["district"],
            },
        })

    log.info("workbench_pois_served", categories=list(requested), district=district, count=len(features))
    return {"type": "FeatureCollection", "features": features}


@router.get("/plot/{plot_id}")
async def get_plot_evaluation(
    plot_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    """Return full 9-section plot evaluation for a given plot_id."""
    result = await build_plot_evaluation(plot_id, session)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Plot '{plot_id}' not found")
    return result
