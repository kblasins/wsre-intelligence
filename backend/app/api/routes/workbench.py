"""Workbench API — plot evaluation endpoint.

Endpoints:
  GET /api/workbench/plot/{plot_id}  — full 9-section plot evaluation JSON
"""
from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import current_active_user
from app.core.database import get_db_session
from app.models.auth import User
from app.services.plot_evaluation import build_plot_evaluation

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/workbench", tags=["workbench"])


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
