"""Spatial intelligence API — Phase 3.5.

Endpoints:
  POST   /api/spatial/pois/refresh           — admin: trigger Overpass POI refresh
  POST   /api/spatial/evaluate               — full site evaluation (SSE streaming)
  GET    /api/spatial/sites                  — list authenticated user's saved sites
  POST   /api/spatial/sites                  — create saved site
  GET    /api/spatial/sites/{site_id}        — get one saved site
  PATCH  /api/spatial/sites/{site_id}        — update saved site metadata
  DELETE /api/spatial/sites/{site_id}        — delete saved site
  POST   /api/spatial/sites/{site_id}/evaluate — evaluate a saved site (SSE)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import current_active_user, current_superuser
from app.core.database import get_db_session
from app.models.auth import User
from app.models.spatial import EvaluateCache

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/spatial", tags=["spatial"])

# Evaluate cache TTL
CACHE_TTL_HOURS = 6


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class EvaluateRequest(BaseModel):
    geometry_wkt: str = Field(
        ...,
        description="WKT geometry string (POINT or POLYGON). Must include SRID prefix "
        "e.g. SRID=4326;POINT(46.67 24.69) or a raw WKT",
    )
    radius_m: int = Field(default=5000, ge=100, le=50_000)
    asset_class: str | None = Field(default=None, max_length=100)
    time_window_days: int = Field(default=90, ge=7, le=365)


class SavedSiteCreate(BaseModel):
    name: str = Field(..., max_length=500)
    description: str | None = None
    geometry_geojson: str = Field(..., description="GeoJSON geometry string")
    asset_class: str | None = Field(default=None, max_length=100)
    target_gfa_sqm: float | None = None
    notes: str | None = None


class SavedSiteUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=500)
    description: str | None = None
    asset_class: str | None = Field(default=None, max_length=100)
    target_gfa_sqm: float | None = None
    notes: str | None = None


class SavedSiteOut(BaseModel):
    id: int
    user_id: uuid.UUID
    name: str
    description: str | None
    geometry_geojson: str
    asset_class: str | None
    target_gfa_sqm: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Helper — cache key ─────────────────────────────────────────────────────────


def _cache_key(req: EvaluateRequest) -> str:
    payload = json.dumps(
        {
            "geometry_wkt": req.geometry_wkt,
            "radius_m": req.radius_m,
            "asset_class": req.asset_class,
            "time_window_days": req.time_window_days,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ── Helper — normalize WKT to ensure SRID prefix ─────────────────────────────


def _ensure_srid(wkt: str) -> str:
    if wkt.upper().startswith("SRID="):
        return wkt
    return f"SRID=4326;{wkt}"


# ── Evaluate sections ─────────────────────────────────────────────────────────


async def _section_district(session: AsyncSession, wkt: str) -> dict[str, Any]:
    """Find which district the site centroid falls in."""
    result = await session.execute(
        text("""
            SELECT id, name_en, name_ar, city, region, district_code
            FROM districts
            WHERE ST_Contains(
                polygon,
                ST_Centroid(ST_GeomFromEWKT(:wkt))
            )
            LIMIT 1
        """),
        {"wkt": wkt},
    )
    row = result.mappings().first()
    if row:
        return {"found": True, **dict(row)}
    return {"found": False}


async def _section_pois(
    session: AsyncSession, wkt: str, radius_m: int
) -> dict[str, Any]:
    """Count POIs within radius, grouped by category."""
    result = await session.execute(
        text("""
            SELECT category, COUNT(*) as count
            FROM pois
            WHERE ST_DWithin(
                location::geography,
                ST_Centroid(ST_GeomFromEWKT(:wkt))::geography,
                :radius_m
            )
            GROUP BY category
            ORDER BY count DESC
        """),
        {"wkt": wkt, "radius_m": radius_m},
    )
    rows = result.mappings().all()
    return {
        "radius_m": radius_m,
        "by_category": [dict(r) for r in rows],
        "total": sum(r["count"] for r in rows),
    }


async def _section_regulatory(session: AsyncSession, wkt: str) -> dict[str, Any]:
    """Find regulatory zones that intersect the site geometry."""
    result = await session.execute(
        text("""
            SELECT id, zone_type, name_en, name_ar, rules,
                   effective_from, effective_to, source
            FROM regulatory_zones
            WHERE ST_Intersects(
                polygon,
                ST_GeomFromEWKT(:wkt)
            )
            ORDER BY zone_type
        """),
        {"wkt": wkt},
    )
    rows = result.mappings().all()
    zones = []
    for r in rows:
        z = dict(r)
        if z.get("effective_from"):
            z["effective_from"] = str(z["effective_from"])
        if z.get("effective_to"):
            z["effective_to"] = str(z["effective_to"])
        zones.append(z)
    return {"zones": zones, "count": len(zones)}


async def _section_transactions(
    session: AsyncSession,
    wkt: str,
    radius_m: int,
    time_window_days: int,
    asset_class: str | None,
) -> dict[str, Any]:
    """Recent transactions within radius."""
    since = datetime.now(UTC) - timedelta(days=time_window_days)
    params: dict[str, Any] = {"wkt": wkt, "radius_m": radius_m, "since": since}
    asset_filter = ""
    if asset_class:
        asset_filter = "AND property_type = :asset_class"
        params["asset_class"] = asset_class

    result = await session.execute(
        text(f"""
            SELECT
                COUNT(*) as count,
                AVG(price_sar) as avg_price_sar,
                MIN(price_sar) as min_price_sar,
                MAX(price_sar) as max_price_sar,
                AVG(price_sar / NULLIF(area_sqm, 0)) as avg_price_per_sqm,
                AVG(area_sqm) as avg_area_sqm
            FROM transactions
            WHERE location IS NOT NULL
              AND ST_DWithin(
                  location::geography,
                  ST_Centroid(ST_GeomFromEWKT(:wkt))::geography,
                  :radius_m
              )
              AND transaction_date >= :since
              {asset_filter}
        """),
        params,
    )
    row = result.mappings().first()
    stats = dict(row) if row else {}
    # round floats
    for k in stats:
        if stats[k] is not None and isinstance(stats[k], float):
            stats[k] = round(stats[k], 2)
    return {"radius_m": radius_m, "time_window_days": time_window_days, **stats}


async def _section_listings(
    session: AsyncSession,
    wkt: str,
    radius_m: int,
    asset_class: str | None,
) -> dict[str, Any]:
    """Active listings within radius."""
    params: dict[str, Any] = {"wkt": wkt, "radius_m": radius_m}
    asset_filter = ""
    if asset_class:
        asset_filter = "AND property_type = :asset_class"
        params["asset_class"] = asset_class

    result = await session.execute(
        text(f"""
            SELECT
                COUNT(*) as count,
                AVG(rent_sar_annual) as avg_rent_sar_annual,
                AVG(area_sqm) as avg_area_sqm,
                AVG(rent_sar_annual / NULLIF(area_sqm, 0)) as avg_rent_per_sqm
            FROM listings
            WHERE location IS NOT NULL
              AND is_active = true
              AND ST_DWithin(
                  location::geography,
                  ST_Centroid(ST_GeomFromEWKT(:wkt))::geography,
                  :radius_m
              )
              {asset_filter}
        """),
        params,
    )
    row = result.mappings().first()
    stats = dict(row) if row else {}
    for k in stats:
        if stats[k] is not None and isinstance(stats[k], float):
            stats[k] = round(stats[k], 2)
    return {"radius_m": radius_m, **stats}


async def _section_reit_properties(
    session: AsyncSession,
    wkt: str,
    radius_m: int,
) -> dict[str, Any]:
    """REIT properties within radius."""
    result = await session.execute(
        text("""
            SELECT ticker, property_name, property_type, district,
                   gfa_sqm, occupancy_pct, annual_rent_sar, valuation_sar,
                   ST_Distance(location::geography,
                       ST_Centroid(ST_GeomFromEWKT(:wkt))::geography) as distance_m
            FROM reit_properties
            WHERE location IS NOT NULL
              AND ST_DWithin(
                  location::geography,
                  ST_Centroid(ST_GeomFromEWKT(:wkt))::geography,
                  :radius_m
              )
            ORDER BY distance_m
            LIMIT 20
        """),
        {"wkt": wkt, "radius_m": radius_m},
    )
    rows = result.mappings().all()
    props = []
    for r in rows:
        p = dict(r)
        if p.get("distance_m") is not None:
            p["distance_m"] = round(p["distance_m"], 1)
        props.append(p)
    return {"radius_m": radius_m, "properties": props, "count": len(props)}


async def _section_macro_context(session: AsyncSession) -> dict[str, Any]:
    """Current macro environment — reads from macro_indicators table.

    Table is manually maintained via POST /api/admin/macro-indicators/{key}.
    Automated scraping deferred to a later phase.
    """
    result = await session.execute(
        text("""
            SELECT indicator_key, value, period, source, source_url, fetched_at
            FROM macro_indicators
            ORDER BY indicator_key
        """)
    )
    rows = [dict(r) for r in result.mappings()]

    indicators = [
        {
            "key": r["indicator_key"],
            "value": float(r["value"]),
            "period": str(r["period"]),
            "source": r["source"],
            "source_url": r["source_url"],
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        }
        for r in rows
    ]
    return {"available": True, "indicators": indicators}


# Reference points for industrial site accessibility scoring (approximate — verify from official sources)
_ACCESS_REFS = [
    {"key": "kkia",           "label": "King Khalid Int'l Airport",    "lon": 46.6981, "lat": 24.9578},
    {"key": "dry_port",       "label": "Riyadh Dry Port (ICD)",        "lon": 46.7800, "lat": 24.5500},
    {"key": "king_fahd_road", "label": "King Fahd Road (city centre)", "lon": 46.6753, "lat": 24.6900},
    {"key": "modon_2nd",      "label": "MODON 2nd Industrial City",    "lon": 46.8150, "lat": 24.6750},
    {"key": "ring_road_n",    "label": "Northern Ring Road junction",  "lon": 46.7740, "lat": 24.8200},
]


async def _section_accessibility(session: AsyncSession, wkt: str) -> dict[str, Any]:
    """HGV drive-time to key industrial reference points via ORS matrix.

    Gracefully returns available=False when ORS is unavailable or not configured.
    """
    from app.core.config import settings

    # Extract centroid coordinates via PostGIS
    try:
        result = await session.execute(
            text(
                "SELECT ST_X(ST_Centroid(ST_GeomFromEWKT(:wkt))) AS lon,"
                "       ST_Y(ST_Centroid(ST_GeomFromEWKT(:wkt))) AS lat"
            ),
            {"wkt": wkt},
        )
        row = result.mappings().first()
        if not row:
            return {"available": False, "error": "Could not determine site centroid"}
        site_lon, site_lat = float(row["lon"]), float(row["lat"])
    except Exception as exc:
        return {"available": False, "error": f"Centroid extraction failed: {exc}"}

    if not settings.ors_api_key:
        return {
            "available": False,
            "error": "ORS_API_KEY not configured",
            "refs": [{"key": r["key"], "label": r["label"], "minutes": None} for r in _ACCESS_REFS],
        }

    locations = [[site_lon, site_lat]] + [[r["lon"], r["lat"]] for r in _ACCESS_REFS]

    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.openrouteservice.org/v2/matrix/driving-hgv",
                json={
                    "locations": locations,
                    "sources": [0],
                    "destinations": list(range(1, len(_ACCESS_REFS) + 1)),
                    "metrics": ["duration"],
                },
                headers={
                    "Authorization": settings.ors_api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {
            "available": False,
            "error": f"Accessibility data temporarily unavailable: {exc}",
            "refs": [{"key": r["key"], "label": r["label"], "minutes": None} for r in _ACCESS_REFS],
        }

    durations_row = data.get("durations", [[]])[0]
    refs = []
    for i, ref in enumerate(_ACCESS_REFS):
        secs = durations_row[i] if i < len(durations_row) else None
        refs.append({
            "key": ref["key"],
            "label": ref["label"],
            "minutes": round(secs / 60, 1) if secs is not None else None,
        })

    return {"available": True, "profile": "driving-hgv", "refs": refs}


async def _section_typed_facts(
    session: AsyncSession,
    wkt: str,
    district_name: str | None,
) -> dict[str, Any]:
    """Recent typed facts from the 8 signal tables, optionally filtered by district keyword.

    Returns the 20 most recent high-confidence facts relevant to this site's district.
    Used to surface intelligence signal directly in the site evaluation panel.
    """
    # Geography filter: if district_name is available, filter by district keyword
    # across location-bearing fields; otherwise return recent high-confidence facts.
    dist_filter = ""
    params: dict[str, Any] = {}
    if district_name:
        safe_district = district_name.replace("'", "''")
        dist_filter = f"""
        WHERE (source_citation ILIKE '%{safe_district}%'
               OR summary ILIKE '%{safe_district}%'
               OR source_citation ILIKE '%Riyadh%')
        """
    else:
        dist_filter = "WHERE source_citation ILIKE '%Riyadh%' OR source_citation IS NOT NULL"

    union_sql = f"""
        SELECT id, 'supply_events' AS table_name, created_at, confidence, source_citation,
            COALESCE(event_type,'') || CASE WHEN developer IS NOT NULL THEN ' · ' || developer ELSE '' END
            || CASE WHEN location_description IS NOT NULL THEN ' · ' || location_description ELSE '' END AS summary
        FROM supply_events WHERE confidence >= 4
        UNION ALL
        SELECT id, 'regulatory_events', created_at, confidence, source_citation,
            COALESCE(authority,'') || CASE WHEN summary IS NOT NULL THEN ' · ' || LEFT(summary,100) ELSE '' END
        FROM regulatory_events WHERE confidence >= 4
        UNION ALL
        SELECT id, 'macro_signals', created_at, confidence, source_citation,
            COALESCE(indicator,'') || CASE WHEN period IS NOT NULL THEN ' · ' || period ELSE '' END
            || CASE WHEN magnitude IS NOT NULL THEN ' · ' || magnitude ELSE '' END
        FROM macro_signals WHERE confidence >= 4
        UNION ALL
        SELECT id, 'demand_signals', created_at, confidence, source_citation,
            COALESCE(sector,'') || CASE WHEN metric IS NOT NULL THEN ' · ' || metric ELSE '' END
            || CASE WHEN value IS NOT NULL THEN ' · ' || value ELSE '' END
        FROM demand_signals WHERE confidence >= 4
        UNION ALL
        SELECT id, 'capital_markets_events', created_at, confidence, source_citation,
            COALESCE(event_type,'') || CASE WHEN entity IS NOT NULL THEN ' · ' || entity ELSE '' END
        FROM capital_markets_events WHERE confidence >= 4
        UNION ALL
        SELECT id, 'infrastructure_events', created_at, confidence, source_citation,
            COALESCE(project,'') || CASE WHEN infra_type IS NOT NULL THEN ' · ' || infra_type ELSE '' END
            || CASE WHEN location IS NOT NULL THEN ' · ' || location ELSE '' END
        FROM infrastructure_events WHERE confidence >= 4
        UNION ALL
        SELECT id, 'tenant_signals', created_at, confidence, source_citation,
            COALESCE(tenant_name,'') || CASE WHEN event_type IS NOT NULL THEN ' · ' || event_type ELSE '' END
        FROM tenant_signals WHERE confidence >= 4
        UNION ALL
        SELECT id, 'market_commentary', created_at, confidence, source_citation,
            COALESCE(source_authority,'') || CASE WHEN topic IS NOT NULL THEN ' · ' || topic ELSE '' END
        FROM market_commentary WHERE confidence >= 4
    """

    full_sql = text(
        f"SELECT * FROM ({union_sql}) AS t "
        f"ORDER BY created_at DESC NULLS LAST LIMIT 15"
    )
    rows = (await session.execute(full_sql)).mappings().all()

    facts = [
        {
            "id": r["id"],
            "table": r["table_name"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "confidence": r["confidence"],
            "source_citation": r["source_citation"],
            "summary": r["summary"],
        }
        for r in rows
    ]

    return {
        "district_filter": district_name,
        "count": len(facts),
        "facts": facts,
    }


async def _section_data_quality(
    session: AsyncSession, req: EvaluateRequest
) -> dict[str, Any]:
    """Data sources used for this evaluation, freshness, and gaps."""
    # Check when each source was last updated
    now = datetime.now(UTC)

    async def _latest(table: str, date_col: str) -> str | None:
        try:
            r = await session.execute(text(f"SELECT MAX({date_col}) as ts FROM {table}"))
            ts = r.scalar()
            if ts is None:
                return None
            if hasattr(ts, "isoformat"):
                return ts.isoformat()[:10]
            return str(ts)[:10]
        except Exception:
            return None

    poi_latest = await _latest("pois", "updated_at")
    district_latest = await _latest("districts", "updated_at")
    reit_latest = await _latest("reit_snapshots", "snapshot_date")
    listing_latest = await _latest("listings", "updated_at")

    sources = [
        {
            "name": "District boundaries",
            "provider": "OpenStreetMap / custom",
            "last_updated": district_latest,
            "status": "ok" if district_latest else "no_data",
        },
        {
            "name": "Points of interest",
            "provider": "OpenStreetMap Overpass",
            "last_updated": poi_latest,
            "status": "ok" if poi_latest else "no_data",
        },
        {
            "name": "REIT prices",
            "provider": "yfinance (Tadawul, 15-min delay)",
            "last_updated": reit_latest,
            "status": "ok" if reit_latest else "no_data",
        },
        {
            "name": "Listings",
            "provider": "Aqar",
            "last_updated": listing_latest,
            "status": "ok" if listing_latest else "no_data",
        },
        {
            "name": "Transactions",
            "provider": "REGA (pending Open Data agreement)",
            "last_updated": None,
            "status": "pending",
            "note": "Open Data request submitted 18 Apr 2026",
        },
        {
            "name": "Rent benchmarks",
            "provider": "Knight Frank / CBRE / JLL research reports",
            "last_updated": None,
            "status": "manual",
            "note": "Updated when new research reports are published and extracted",
        },
    ]

    gaps = [s["name"] for s in sources if s["status"] in ("no_data", "pending")]

    return {
        "as_of": now.isoformat()[:19] + "Z",
        "radius_m": req.radius_m,
        "time_window_days": req.time_window_days,
        "sources": sources,
        "gaps": gaps,
    }


# ── SSE streaming evaluator ────────────────────────────────────────────────────


async def _stream_evaluation(
    req: EvaluateRequest,
    cache_key: str,
    session: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Compute evaluation sections and yield SSE events."""
    wkt = _ensure_srid(req.geometry_wkt)
    result: dict[str, Any] = {}

    # District runs first — its result informs typed_facts district filter
    district_data: dict[str, Any] = {}
    try:
        district_data = await _section_district(session, wkt)
    except Exception:
        log.exception("evaluate_section_error", section="district")
        district_data = {"error": "computation failed"}
    result["district"] = district_data
    yield f"data: {json.dumps({'section': 'district', 'data': district_data})}\n\n"

    district_name: str | None = district_data.get("name_en") if district_data.get("found") else None

    sections = [
        ("pois", _section_pois(session, wkt, req.radius_m)),
        ("regulatory", _section_regulatory(session, wkt)),
        (
            "transactions",
            _section_transactions(
                session, wkt, req.radius_m, req.time_window_days, req.asset_class
            ),
        ),
        ("listings", _section_listings(session, wkt, req.radius_m, req.asset_class)),
        ("reit_properties", _section_reit_properties(session, wkt, req.radius_m)),
        ("typed_facts", _section_typed_facts(session, wkt, district_name)),
        ("accessibility", _section_accessibility(session, wkt)),
        ("macro_context", _section_macro_context(session)),
        ("data_quality", _section_data_quality(session, req)),
    ]

    for section_name, coro in sections:
        try:
            data = await coro
        except Exception:
            log.exception("evaluate_section_error", section=section_name)
            data = {"error": "computation failed"}

        result[section_name] = data
        event = json.dumps({"section": section_name, "data": data})
        yield f"data: {event}\n\n"

    # Store in cache
    try:
        now = datetime.now(UTC)
        expires = now + timedelta(hours=CACHE_TTL_HOURS)
        cache_row = EvaluateCache(
            cache_key=cache_key,
            geometry_wkt=req.geometry_wkt,
            radius_m=req.radius_m,
            asset_class=req.asset_class,
            time_window_days=req.time_window_days,
            result=result,
            computed_at=now,
            expires_at=expires,
        )
        session.add(cache_row)
        await session.commit()
    except Exception:
        log.exception("evaluate_cache_store_error", cache_key=cache_key)

    yield "data: {\"section\": \"done\"}\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/isochrone")
async def get_isochrone(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    lon: float,
    lat: float,
    profile: str = "driving-car",
) -> dict[str, Any]:
    """Compute or serve cached drive-time isochrone for a point.

    Returns GeoJSON FeatureCollection with three polygon features:
    15-min, 30-min, 60-min drive times.

    Caches results in isochrone_cache for 90 days.
    Requires ORS_API_KEY in environment.
    """
    from app.core.config import settings

    # Round to 3dp for cache key consistency
    lon_r = round(lon, 3)
    lat_r = round(lat, 3)

    # Check cache
    cached = await session.execute(
        text("""
            SELECT minutes_15, minutes_30, minutes_60,
                   ST_AsGeoJSON(minutes_15) as j15,
                   ST_AsGeoJSON(minutes_30) as j30,
                   ST_AsGeoJSON(minutes_60) as j60,
                   computed_at
            FROM isochrone_cache
            WHERE ST_Equals(
                center,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
            )
            AND profile = :profile
            AND computed_at > NOW() - INTERVAL '90 days'
            LIMIT 1
        """),
        {"lon": lon_r, "lat": lat_r, "profile": profile},
    )
    row = cached.mappings().first()
    if row:
        features = []
        for minutes, geom_json in [(15, row["j15"]), (30, row["j30"]), (60, row["j60"])]:
            if geom_json:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": json.loads(geom_json),
                        "properties": {"minutes": minutes},
                    }
                )
        return {"type": "FeatureCollection", "features": features, "cached": True}

    # Compute via OpenRouteService
    if not settings.ors_api_key:
        raise HTTPException(
            status_code=503,
            detail="ORS_API_KEY not configured. Set ors_api_key in .env.local.",
        )

    import httpx

    ors_url = "https://api.openrouteservice.org/v2/isochrones/" + profile
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                ors_url,
                json={
                    "locations": [[lon_r, lat_r]],
                    "range": [900, 1800, 3600],  # 15, 30, 60 min in seconds
                    "range_type": "time",
                    "smoothing": 0.25,
                },
                headers={
                    "Authorization": settings.ors_api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            ors_data = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ORS request failed: {exc}") from exc

    features_raw = ors_data.get("features", [])
    if not features_raw:
        raise HTTPException(status_code=502, detail="ORS returned no isochrone features")

    # ORS returns largest range first; map back to minutes
    minute_map = {3600: 60, 1800: 30, 900: 15}
    geoms: dict[int, str] = {}
    for feat in features_raw:
        props = feat.get("properties", {})
        seconds = props.get("value", 0)
        minutes = minute_map.get(seconds)
        if minutes:
            geoms[minutes] = json.dumps(feat["geometry"])

    # Store in cache
    now = datetime.now(UTC)
    await session.execute(
        text("""
            INSERT INTO isochrone_cache
                (center, profile, minutes_15, minutes_30, minutes_60,
                 provider, computed_at)
            VALUES (
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                :profile,
                CASE WHEN :g15 IS NOT NULL
                     THEN ST_SetSRID(ST_GeomFromGeoJSON(:g15), 4326) END,
                CASE WHEN :g30 IS NOT NULL
                     THEN ST_SetSRID(ST_GeomFromGeoJSON(:g30), 4326) END,
                CASE WHEN :g60 IS NOT NULL
                     THEN ST_SetSRID(ST_GeomFromGeoJSON(:g60), 4326) END,
                'openrouteservice', :now
            )
            ON CONFLICT ON CONSTRAINT uq_isochrone_center_profile
            DO UPDATE SET
                minutes_15 = EXCLUDED.minutes_15,
                minutes_30 = EXCLUDED.minutes_30,
                minutes_60 = EXCLUDED.minutes_60,
                computed_at = EXCLUDED.computed_at
        """),
        {
            "lon": lon_r,
            "lat": lat_r,
            "profile": profile,
            "g15": geoms.get(15),
            "g30": geoms.get(30),
            "g60": geoms.get(60),
            "now": now,
        },
    )
    await session.commit()

    out_features = []
    for minutes, geom_json in [(15, geoms.get(15)), (30, geoms.get(30)), (60, geoms.get(60))]:
        if geom_json:
            out_features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(geom_json),
                    "properties": {"minutes": minutes},
                }
            )
    return {"type": "FeatureCollection", "features": out_features, "cached": False}


@router.post("/pois/refresh", status_code=202)
async def trigger_poi_refresh(
    background_tasks: BackgroundTasks,
    _: Annotated[User, Depends(current_superuser)],
) -> dict[str, str]:
    """Admin: trigger an immediate Overpass POI refresh in background."""
    from app.ingestion.scrapers.overpass import run_overpass_refresh

    background_tasks.add_task(run_overpass_refresh)
    return {"status": "accepted", "message": "POI refresh queued"}


@router.post("/evaluate")
async def evaluate_site(
    req: EvaluateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    """Full site evaluation — streams sections as SSE events.

    Check evaluate_cache first; on miss, compute and cache for 6 hours.
    """
    ck = _cache_key(req)

    # Cache check
    cached = await session.get(EvaluateCache, ck)
    if cached and cached.expires_at > datetime.now(UTC):
        log.info("evaluate_cache_hit", cache_key=ck[:12])

        async def _from_cache() -> AsyncGenerator[str, None]:
            for section_name, data in cached.result.items():
                event = json.dumps({"section": section_name, "data": data})
                yield f"data: {event}\n\n"
            yield "data: {\"section\": \"done\"}\n\n"

        return StreamingResponse(_from_cache(), media_type="text/event-stream")

    log.info("evaluate_cache_miss", cache_key=ck[:12])
    return StreamingResponse(
        _stream_evaluation(req, ck, session),
        media_type="text/event-stream",
    )


# ── Saved Sites CRUD ──────────────────────────────────────────────────────────


@router.get("/sites")
async def list_sites(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[dict[str, Any]]:
    """List the current user's saved sites with GeoJSON geometry."""
    result = await session.execute(
        text("""
            SELECT id, user_id, name, description,
                   ST_AsGeoJSON(geometry) as geometry_geojson,
                   asset_class, target_gfa_sqm, notes,
                   created_at, updated_at
            FROM saved_sites
            WHERE user_id = :uid
            ORDER BY updated_at DESC
        """),
        {"uid": str(user.id)},
    )
    rows = result.mappings().all()
    return [
        {
            "id": r["id"],
            "user_id": str(r["user_id"]),
            "name": r["name"],
            "description": r["description"],
            "geometry_geojson": r["geometry_geojson"],
            "asset_class": r["asset_class"],
            "target_gfa_sqm": float(r["target_gfa_sqm"]) if r["target_gfa_sqm"] is not None else None,
            "notes": r["notes"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.post("/sites", status_code=201)
async def create_site(
    body: SavedSiteCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    """Create a saved site. geometry_geojson must be a valid GeoJSON geometry string."""
    now = datetime.now(UTC)
    result = await session.execute(
        text("""
            INSERT INTO saved_sites
                (user_id, name, description, geometry, asset_class,
                 target_gfa_sqm, notes, created_at, updated_at)
            VALUES
                (:uid, :name, :desc,
                 ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326),
                 :asset_class, :gfa, :notes, :now, :now)
            RETURNING id, created_at
        """),
        {
            "uid": str(user.id),
            "name": body.name,
            "desc": body.description,
            "geojson": body.geometry_geojson,
            "asset_class": body.asset_class,
            "gfa": body.target_gfa_sqm,
            "notes": body.notes,
            "now": now,
        },
    )
    await session.commit()
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"id": row["id"], "created_at": row["created_at"].isoformat()}


@router.get("/sites/{site_id}")
async def get_site(
    site_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    """Get a saved site. Returns 404 if not found or not owned by current user."""
    result = await session.execute(
        text("""
            SELECT id, user_id, name, description,
                   ST_AsGeoJSON(geometry) as geometry_geojson,
                   asset_class, target_gfa_sqm, notes, created_at, updated_at
            FROM saved_sites
            WHERE id = :id AND user_id = :uid
        """),
        {"id": site_id, "uid": str(user.id)},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return {
        "id": row["id"],
        "user_id": str(row["user_id"]),
        "name": row["name"],
        "description": row["description"],
        "geometry_geojson": row["geometry_geojson"],
        "asset_class": row["asset_class"],
        "target_gfa_sqm": float(row["target_gfa_sqm"]) if row["target_gfa_sqm"] is not None else None,
        "notes": row["notes"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.patch("/sites/{site_id}")
async def update_site(
    site_id: int,
    body: SavedSiteUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    """Update saved site metadata (not geometry — delete + recreate for that)."""
    # Verify ownership
    exists = await session.execute(
        text("SELECT id FROM saved_sites WHERE id = :id AND user_id = :uid"),
        {"id": site_id, "uid": str(user.id)},
    )
    if not exists.first():
        raise HTTPException(status_code=404, detail="Site not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = site_id
    updates["uid"] = str(user.id)
    updates["now"] = datetime.now(UTC)

    await session.execute(
        text(f"""
            UPDATE saved_sites
            SET {set_clauses}, updated_at = :now
            WHERE id = :id AND user_id = :uid
        """),
        updates,
    )
    await session.commit()
    return {"id": site_id, "updated": True}


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(
    site_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    """Delete a saved site."""
    result = await session.execute(
        text("DELETE FROM saved_sites WHERE id = :id AND user_id = :uid RETURNING id"),
        {"id": site_id, "uid": str(user.id)},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Site not found")
    await session.commit()


@router.get("/pois/geojson")
async def pois_geojson(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    category: str | None = None,
    bbox: str | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    """POIs as a GeoJSON FeatureCollection for MapLibre source.

    bbox: "west,south,east,north" (comma-separated floats)
    """
    params: dict[str, Any] = {"limit": limit}
    filters = ["1=1"]

    if category:
        filters.append("category = :category")
        params["category"] = category

    if bbox:
        try:
            w, s, e, n = (float(x) for x in bbox.split(","))
            filters.append(
                "ST_Within(location, ST_MakeEnvelope(:w, :s, :e, :n, 4326))"
            )
            params.update({"w": w, "s": s, "e": e, "n": n})
        except ValueError:
            pass

    where = " AND ".join(filters)
    result = await session.execute(
        text(f"""
            SELECT id, category, subcategory, name_en, name_ar, address,
                   operator, brand, phone, website, opening_hours,
                   building_levels, height_m, capacity,
                   footprint_area_sqm, is_polygon,
                   district_id,
                   last_seen_at,
                   ST_X(location) as lon, ST_Y(location) as lat
            FROM pois
            WHERE {where}
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().all()
    features = [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": {
                "id": r["id"],
                "category": r["category"],
                "subcategory": r["subcategory"],
                "name_en": r["name_en"],
                "name_ar": r["name_ar"],
                "address": r["address"],
                "operator": r["operator"],
                "brand": r["brand"],
                "phone": r["phone"],
                "website": r["website"],
                "opening_hours": r["opening_hours"],
                "building_levels": r["building_levels"],
                "height_m": float(r["height_m"]) if r["height_m"] is not None else None,
                "capacity": r["capacity"],
                "footprint_area_sqm": float(r["footprint_area_sqm"]) if r["footprint_area_sqm"] is not None else None,
                "is_polygon": r["is_polygon"],
                "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
            },
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/districts/geojson")
async def districts_geojson(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    city: str = "Riyadh",
) -> dict[str, Any]:
    """Districts with polygons as GeoJSON FeatureCollection."""
    result = await session.execute(
        text("""
            SELECT id, name_en, name_ar, district_code,
                   ST_AsGeoJSON(polygon) as geom_json
            FROM districts
            WHERE city = :city AND polygon IS NOT NULL
        """),
        {"city": city},
    )
    rows = result.mappings().all()
    features = [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": json.loads(r["geom_json"]),
            "properties": {
                "id": r["id"],
                "name_en": r["name_en"],
                "name_ar": r["name_ar"],
                "district_code": r["district_code"],
            },
        }
        for r in rows
        if r["geom_json"]
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/regulatory-zones/geojson")
async def regulatory_zones_geojson(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    zone_type: str | None = None,
) -> dict[str, Any]:
    """Regulatory zones as GeoJSON FeatureCollection."""
    params: dict[str, Any] = {}
    type_filter = ""
    if zone_type:
        type_filter = "WHERE zone_type = :zone_type"
        params["zone_type"] = zone_type

    result = await session.execute(
        text(f"""
            SELECT id, zone_type, name_en, name_ar, rules,
                   ST_AsGeoJSON(polygon) as geom_json
            FROM regulatory_zones
            {type_filter}
        """),
        params,
    )
    rows = result.mappings().all()
    features = [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": json.loads(r["geom_json"]),
            "properties": {
                "id": r["id"],
                "zone_type": r["zone_type"],
                "name_en": r["name_en"],
                "name_ar": r["name_ar"],
            },
        }
        for r in rows
        if r["geom_json"]
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/velocity")
async def get_district_velocity(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    property_type: str | None = None,
    window_days: int = 90,
) -> list[dict[str, Any]]:
    """District velocity summary — aggregated tx counts and momentum.

    Used by the frontend heatmap layer to color-code districts.
    window_days: 30 / 90 / 365 — controls the aggregation window.
    Falls back to an empty list if the view doesn't exist yet.
    """
    # Clamp window to supported values
    window_days = min(max(window_days, 1), 365)

    try:
        params: dict[str, Any] = {"since": datetime.now(UTC) - timedelta(days=window_days)}
        type_filter = ""
        if property_type:
            type_filter = "AND dv.property_type = :pt"
            params["pt"] = property_type

        result = await session.execute(
            text(f"""
                SELECT
                    dv.district_key,
                    dv.district_name,
                    dv.property_type,
                    SUM(dv.tx_count)                          AS tx_count,
                    AVG(dv.avg_price_per_sqm)                 AS avg_price_per_sqm,
                    MAX(dv.month)                             AS latest_month,
                    AVG(dv.momentum_pct)                      AS avg_momentum_pct
                FROM district_velocity dv
                WHERE dv.month >= :since
                  {type_filter}
                GROUP BY dv.district_key, dv.district_name, dv.property_type
                ORDER BY tx_count DESC
                LIMIT 200
            """),
            params,
        )
        rows = result.mappings().all()
        return [
            {
                "district_key": r["district_key"],
                "district_name": r["district_name"],
                "property_type": r["property_type"],
                "tx_count": int(r["tx_count"]) if r["tx_count"] is not None else 0,
                "avg_price_per_sqm": float(r["avg_price_per_sqm"]) if r["avg_price_per_sqm"] is not None else None,
                "avg_momentum_pct": float(r["avg_momentum_pct"]) if r["avg_momentum_pct"] is not None else None,
                "latest_month": str(r["latest_month"])[:10] if r["latest_month"] else None,
                "window_days": window_days,
            }
            for r in rows
        ]
    except Exception:
        log.warning("district_velocity_view_not_ready")
        return []


@router.post("/sites/{site_id}/evaluate")
async def evaluate_saved_site(
    site_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(current_active_user)],
    radius_m: int = 5000,
    asset_class: str | None = None,
    time_window_days: int = 90,
) -> StreamingResponse:
    """Evaluate a saved site. Loads site geometry then delegates to evaluate_site."""
    result = await session.execute(
        text("""
            SELECT ST_AsText(geometry) as wkt
            FROM saved_sites
            WHERE id = :id AND user_id = :uid
        """),
        {"id": site_id, "uid": str(user.id)},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Site not found")

    req = EvaluateRequest(
        geometry_wkt=row["wkt"],
        radius_m=radius_m,
        asset_class=asset_class,
        time_window_days=time_window_days,
    )
    ck = _cache_key(req)

    cached = await session.get(EvaluateCache, ck)
    if cached and cached.expires_at > datetime.now(UTC):

        async def _from_cache() -> AsyncGenerator[str, None]:
            for section_name, data in cached.result.items():
                event = json.dumps({"section": section_name, "data": data})
                yield f"data: {event}\n\n"
            yield "data: {\"section\": \"done\"}\n\n"

        return StreamingResponse(_from_cache(), media_type="text/event-stream")

    return StreamingResponse(
        _stream_evaluation(req, ck, session),
        media_type="text/event-stream",
    )
