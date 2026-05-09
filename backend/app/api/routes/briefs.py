"""Weekly brief read endpoints."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.api.routes.auth import current_active_user
from app.core.database import get_db_session
from app.models.brief import WeeklyBrief

router = APIRouter(prefix="/api", tags=["briefs"])


def _brief_dict(b: WeeklyBrief) -> dict:
    return {
        "id": b.id,
        "week_ending": b.week_ending.isoformat(),
        "brief_text": b.brief_text,
        "brief_json": b.brief_json,
        "model_id": b.model_id,
        "cost_usd": float(b.cost_usd),
        "generated_at": b.generated_at.isoformat(),
        "pdf_uri": b.pdf_uri,
    }


@router.get("/briefs/latest")
async def latest_brief(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[object, Depends(current_active_user)],
) -> dict:
    """Most recent weekly brief — used by the dashboard brief panel."""
    result = await session.execute(
        select(WeeklyBrief).order_by(WeeklyBrief.week_ending.desc()).limit(1)
    )
    brief = result.scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief generated yet")
    return _brief_dict(brief)


@router.get("/briefs")
async def list_briefs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[object, Depends(current_active_user)],
) -> list[dict]:
    """All briefs, most recent first — brief index page."""
    result = await session.execute(
        select(WeeklyBrief).order_by(WeeklyBrief.week_ending.desc()).limit(52)
    )
    briefs = list(result.scalars())
    return [
        {
            "id": b.id,
            "week_ending": b.week_ending.isoformat(),
            "executive_summary": b.brief_json.get("executive_summary", ""),
            "model_id": b.model_id,
            "cost_usd": float(b.cost_usd),
            "generated_at": b.generated_at.isoformat(),
            "has_pdf": b.pdf_uri is not None,
        }
        for b in briefs
    ]


@router.get("/briefs/{brief_id}")
async def get_brief(
    brief_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[object, Depends(current_active_user)],
) -> dict:
    """Full brief by ID."""
    result = await session.execute(select(WeeklyBrief).where(WeeklyBrief.id == brief_id))
    brief = result.scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return _brief_dict(brief)


@router.get("/briefs/{brief_id}/pdf")
async def get_brief_pdf(
    brief_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[object, Depends(current_active_user)],
) -> Response:
    """Download or redirect to the brief PDF.

    If pdf_uri is an S3/GCS URL, redirects there (presigned or public).
    If it's a local file path, serves the bytes directly.
    Returns 404 if the brief has no PDF yet.
    """
    result = await session.execute(select(WeeklyBrief).where(WeeklyBrief.id == brief_id))
    brief = result.scalar_one_or_none()
    if brief is None or not brief.pdf_uri:
        raise HTTPException(status_code=404, detail="PDF not available for this brief")

    uri = brief.pdf_uri

    # If it's an S3/GCS/HTTP URI, redirect
    if uri.startswith(("http://", "https://", "s3://", "gs://")):
        return RedirectResponse(url=uri)

    # Local blob — decompress and serve via blob store
    from app.core.storage import download_raw

    try:
        pdf_bytes = await download_raw(uri)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    week = brief.week_ending.isoformat()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="white-star-brief-{week}.pdf"'},
    )


@router.post("/briefs/trigger")
async def trigger_brief(
    background_tasks: BackgroundTasks,
    _user: Annotated[object, Depends(current_active_user)],
    week_ending: date | None = None,
) -> dict:
    """Manually trigger a brief generation run (runs in background).

    Useful for regenerating or testing without waiting for the Sunday scheduler.
    Requires auth. The run is non-blocking — poll /api/briefs to see the result.
    """
    from app.briefing.orchestrator import run_weekly_brief

    target = week_ending or date.today()

    async def _run() -> None:
        await run_weekly_brief(target)

    background_tasks.add_task(asyncio.ensure_future, _run())
    return {"status": "triggered", "week_ending": target.isoformat()}
