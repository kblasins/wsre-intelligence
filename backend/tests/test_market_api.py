"""Tests for market data read endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from app.models.market import ReitSnapshot

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.unit
async def test_stats_endpoint_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reit_snapshots"] == 0
    assert body["transactions"] == 0
    assert body["listings"] == 0
    assert body["news_articles"] == 0


@pytest.mark.unit
async def test_reit_snapshots_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/reit-snapshots")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.unit
async def test_reit_snapshots_latest_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/reit-snapshots/latest")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.unit
async def test_reit_snapshots_with_data(api_client: AsyncClient, db_session: AsyncSession) -> None:
    row = ReitSnapshot(
        ticker="4331.SR",
        snapshot_date=date(2026, 4, 16),
        price_sar=10.5,
        raw_uri="local://test",
        extracted_at=datetime.now(UTC),
        raw_json={"name": "AlJazira Mawten REIT", "industrial": "yes"},
    )
    db_session.add(row)
    await db_session.flush()

    resp = await api_client.get("/api/reit-snapshots?ticker=4331.SR")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["ticker"] == "4331.SR"
    assert body[0]["price_sar"] == pytest.approx(10.5)


@pytest.mark.unit
async def test_reit_snapshots_latest_returns_latest_per_ticker(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    for d, price in [(date(2026, 4, 15), 10.0), (date(2026, 4, 16), 10.5)]:
        db_session.add(
            ReitSnapshot(
                ticker="4331.SR",
                snapshot_date=d,
                price_sar=price,
                raw_uri="local://test",
                extracted_at=datetime.now(UTC),
                raw_json={"name": "AlJazira Mawten REIT", "industrial": "yes"},
            )
        )
    await db_session.flush()

    resp = await api_client.get("/api/reit-snapshots/latest")
    assert resp.status_code == 200
    body = resp.json()
    tickers = [r["ticker"] for r in body]
    assert "4331.SR" in tickers
    match = next(r for r in body if r["ticker"] == "4331.SR")
    assert match["price_sar"] == pytest.approx(10.5)
