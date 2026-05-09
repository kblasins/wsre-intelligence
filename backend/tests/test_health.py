"""Health endpoint tests — the simplest possible canary for the API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.unit
async def test_health_returns_ok(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "env" in body


@pytest.mark.unit
async def test_health_db_returns_ok(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/health/db")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
