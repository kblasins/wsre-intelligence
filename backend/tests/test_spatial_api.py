"""Tests for the Phase 3.5 spatial API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


# ── /api/spatial/districts/geojson ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_districts_geojson_returns_feature_collection(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/spatial/districts/geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)


# ── /api/spatial/pois/geojson ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pois_geojson_returns_feature_collection(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/spatial/pois/geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)


@pytest.mark.asyncio
async def test_pois_geojson_category_filter(
    api_client: AsyncClient, db_session
) -> None:
    from datetime import UTC, datetime
    from sqlalchemy import text

    # Insert a test POI directly via SQL (geometry column requires ST_* function)
    await db_session.execute(
        text("""
            INSERT INTO pois
                (osm_id, osm_type, category, subcategory, location,
                 tags, source, first_seen_at, last_seen_at)
            VALUES
                (12345, 'node', 'industrial', 'warehouse',
                 ST_SetSRID(ST_MakePoint(46.675, 24.688), 4326),
                 '{}', 'osm_overpass', :now, :now)
            ON CONFLICT ON CONSTRAINT uq_poi_source_osm DO NOTHING
        """),
        {"now": datetime.now(UTC)},
    )
    await db_session.commit()

    resp = await api_client.get("/api/spatial/pois/geojson?category=industrial")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    # All returned features should be industrial
    for feat in data["features"]:
        assert feat["properties"]["category"] == "industrial"


# ── /api/spatial/regulatory-zones/geojson ────────────────────────────────────


@pytest.mark.asyncio
async def test_regulatory_zones_geojson_returns_feature_collection(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/spatial/regulatory-zones/geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)


# ── /api/spatial/velocity ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_velocity_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/spatial/velocity")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── /api/spatial/evaluate ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_streams_sections(authed_client: AsyncClient) -> None:
    """Evaluate endpoint returns SSE stream with expected section names."""
    resp = await authed_client.post(
        "/api/spatial/evaluate",
        json={
            "geometry_wkt": "POINT(46.675 24.688)",
            "radius_m": 5000,
            "time_window_days": 90,
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    import json

    sections = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            sections.append(payload["section"])

    expected = {"district", "pois", "regulatory", "transactions", "listings", "reit_properties", "done"}
    assert expected.issubset(set(sections))


@pytest.mark.asyncio
async def test_evaluate_invalid_wkt_still_returns_stream(
    authed_client: AsyncClient,
) -> None:
    """Even with an empty/invalid area, we get a stream (sections may be empty)."""
    resp = await authed_client.post(
        "/api/spatial/evaluate",
        json={
            "geometry_wkt": "POINT(0 0)",  # middle of ocean
            "radius_m": 100,
            "time_window_days": 30,
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


# ── /api/spatial/sites (CRUD) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sites_list_requires_auth(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/spatial/sites")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sites_create_and_list(authed_client: AsyncClient) -> None:
    # Create
    create_resp = await authed_client.post(
        "/api/spatial/sites",
        json={
            "name": "Test Industrial Site",
            "geometry_geojson": '{"type":"Point","coordinates":[46.675,24.688]}',
            "asset_class": "warehouse",
        },
    )
    assert create_resp.status_code == 201
    site_id = create_resp.json()["id"]
    assert isinstance(site_id, int)

    # List
    list_resp = await authed_client.get("/api/spatial/sites")
    assert list_resp.status_code == 200
    sites = list_resp.json()
    assert any(s["id"] == site_id for s in sites)


@pytest.mark.asyncio
async def test_sites_get(authed_client: AsyncClient) -> None:
    create_resp = await authed_client.post(
        "/api/spatial/sites",
        json={
            "name": "Get Test Site",
            "geometry_geojson": '{"type":"Point","coordinates":[46.70,24.70]}',
        },
    )
    site_id = create_resp.json()["id"]

    resp = await authed_client.get(f"/api/spatial/sites/{site_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test Site"


@pytest.mark.asyncio
async def test_sites_patch(authed_client: AsyncClient) -> None:
    create_resp = await authed_client.post(
        "/api/spatial/sites",
        json={
            "name": "Patch Before",
            "geometry_geojson": '{"type":"Point","coordinates":[46.70,24.70]}',
        },
    )
    site_id = create_resp.json()["id"]

    patch_resp = await authed_client.patch(
        f"/api/spatial/sites/{site_id}",
        json={"name": "Patch After", "notes": "Updated"},
    )
    assert patch_resp.status_code == 200

    get_resp = await authed_client.get(f"/api/spatial/sites/{site_id}")
    assert get_resp.json()["name"] == "Patch After"
    assert get_resp.json()["notes"] == "Updated"


@pytest.mark.asyncio
async def test_sites_delete(authed_client: AsyncClient) -> None:
    create_resp = await authed_client.post(
        "/api/spatial/sites",
        json={
            "name": "Delete Me",
            "geometry_geojson": '{"type":"Point","coordinates":[46.71,24.71]}',
        },
    )
    site_id = create_resp.json()["id"]

    del_resp = await authed_client.delete(f"/api/spatial/sites/{site_id}")
    assert del_resp.status_code == 204

    get_resp = await authed_client.get(f"/api/spatial/sites/{site_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_sites_get_404_for_other_user(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/spatial/sites/99999999")
    assert resp.status_code == 404
