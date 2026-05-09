"""SQLAlchemy ORM models.

All models are imported here so Alembic's env.py can discover them
via `from app.models import *` (Base.metadata is the source of truth).
"""

from __future__ import annotations

from app.models.auth import User
from app.models.brief import WeeklyBrief
from app.models.ingestion import RawIngestOutbox, SourceRegistry
from app.models.llm import LLMCall
from app.models.market import (
    DistrictAlias,
    Listing,
    NewsArticle,
    ReitSnapshot,
    RentIndex,
    Tender,
    Transaction,
)
from app.models.review import ReviewQueue
from app.models.spatial import (
    POI,
    District,
    EvaluateCache,
    IsochroneCache,
    RegulatoryZone,
    REITProperty,
    SavedSite,
)

__all__ = [
    "POI",
    "District",
    "DistrictAlias",
    "EvaluateCache",
    "IsochroneCache",
    "LLMCall",
    "Listing",
    "NewsArticle",
    "REITProperty",
    "RawIngestOutbox",
    "RegulatoryZone",
    "ReitSnapshot",
    "RentIndex",
    "ReviewQueue",
    "SavedSite",
    "SourceRegistry",
    "Tender",
    "Transaction",
    "User",
    "WeeklyBrief",
]
