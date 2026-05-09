"""Tests for /api/briefs endpoints."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brief import WeeklyBrief


@pytest.mark.asyncio
async def test_latest_brief_404_when_empty(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/briefs/latest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_briefs_empty(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/briefs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_latest_brief_returns_most_recent(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    older = WeeklyBrief(
        week_ending=date(2026, 2, 2),
        brief_text="Older brief",
        brief_json={"executive_summary": "Old summary"},
        model_id="claude-opus-4-6",
        prompt_sha="aabbccdd1234",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.05,
    )
    newer = WeeklyBrief(
        week_ending=date(2026, 2, 9),
        brief_text="Newer brief",
        brief_json={"executive_summary": "New summary"},
        model_id="claude-opus-4-6",
        prompt_sha="aabbccdd1234",
        input_tokens=1200,
        output_tokens=600,
        cost_usd=0.06,
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await authed_client.get("/api/briefs/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["week_ending"] == "2026-02-09"
    assert data["brief_json"]["executive_summary"] == "New summary"
    assert "cost_usd" in data
    assert "model_id" in data


@pytest.mark.asyncio
async def test_list_briefs_ordered_most_recent_first(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    for d in [date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16)]:
        db_session.add(
            WeeklyBrief(
                week_ending=d,
                brief_text="Brief",
                brief_json={},
                model_id="claude-opus-4-6",
                prompt_sha="aabbccdd1234",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
            )
        )
    await db_session.commit()

    resp = await authed_client.get("/api/briefs")
    assert resp.status_code == 200
    dates = [r["week_ending"] for r in resp.json()]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_get_brief_by_id(authed_client: AsyncClient, db_session: AsyncSession) -> None:
    brief = WeeklyBrief(
        week_ending=date(2026, 4, 6),
        brief_text="Full brief text",
        brief_json={"executive_summary": "Summary here"},
        model_id="claude-opus-4-6",
        prompt_sha="aabbccdd1234",
        input_tokens=800,
        output_tokens=400,
        cost_usd=0.03,
    )
    db_session.add(brief)
    await db_session.commit()
    await db_session.refresh(brief)

    resp = await authed_client.get(f"/api/briefs/{brief.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["brief_text"] == "Full brief text"
    assert data["brief_json"]["executive_summary"] == "Summary here"


@pytest.mark.asyncio
async def test_get_brief_404_unknown_id(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/briefs/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    """Briefs endpoints require auth — unauthenticated gets 401."""
    resp = await api_client.get("/api/briefs/latest")
    assert resp.status_code == 401

    resp = await api_client.get("/api/briefs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pdf_endpoint_404_when_no_pdf(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/briefs/{id}/pdf returns 404 when pdf_uri is None."""
    brief = WeeklyBrief(
        week_ending=date(2026, 5, 11),
        brief_text="No PDF brief",
        brief_json={},
        model_id="claude-opus-4-6",
        prompt_sha="aabbccdd1234",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        pdf_uri=None,
    )
    db_session.add(brief)
    await db_session.commit()
    await db_session.refresh(brief)

    resp = await authed_client.get(f"/api/briefs/{brief.id}/pdf")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pdf_endpoint_404_for_unknown_id(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/briefs/999888/pdf")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pdf_endpoint_unauthenticated_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/briefs/1/pdf")
    assert resp.status_code == 401
