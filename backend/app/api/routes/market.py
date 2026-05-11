"""Market data read endpoints.

All endpoints are read-only GET routes. Data enters the system only via
the ingestion scrapers (write path), never via the API.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.database import get_db_session
from app.models.facts import (
    CapitalMarketsEvent,
    DemandSignal,
    InfrastructureEvent,
    MacroSignal,
    MarketCommentary,
    RegulatoryEvent,
    SupplyEvent,
    TenantSignal,
)
from app.models.market import (
    DistrictAlias,
    Listing,
    NewsArticle,
    ReitSnapshot,
    RentIndex,
    Tender,
    Transaction,
)

router = APIRouter(prefix="/api", tags=["market"])


# ── REIT snapshots ─────────────────────────────────────────────────────────────


@router.get("/reit-snapshots")
async def list_reit_snapshots(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ticker: str | None = Query(None, description="Filter by ticker, e.g. 4331.SR"),
    since: date | None = Query(None, description="Only snapshots on or after this date"),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict]:
    """Latest REIT price snapshots from Tadawul (15-min delayed via yfinance)."""
    stmt = select(ReitSnapshot).order_by(desc(ReitSnapshot.snapshot_date), ReitSnapshot.ticker)
    if ticker:
        stmt = stmt.where(ReitSnapshot.ticker == ticker)
    if since:
        stmt = stmt.where(ReitSnapshot.snapshot_date >= since)
    stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "snapshot_date": r.snapshot_date.isoformat(),
            "price_sar": float(r.price_sar) if r.price_sar is not None else None,
            "nav_per_unit_sar": float(r.nav_per_unit_sar)
            if r.nav_per_unit_sar is not None
            else None,
            "nav_discount_pct": float(r.nav_discount_pct)
            if r.nav_discount_pct is not None
            else None,
            "distribution_per_unit_sar": float(r.distribution_per_unit_sar)
            if r.distribution_per_unit_sar is not None
            else None,
            "occupancy_pct": float(r.occupancy_pct) if r.occupancy_pct is not None else None,
            "raw_json": r.raw_json,
            "source_id": r.source_id,
            "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
        }
        for r in rows
    ]


@router.get("/reit-snapshots/latest")
async def latest_reit_snapshots(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """Most recent snapshot per ticker — used by the REIT dashboard cards."""
    # Subquery: max snapshot_date per ticker
    from sqlalchemy import func

    subq = (
        select(ReitSnapshot.ticker, func.max(ReitSnapshot.snapshot_date).label("max_date"))
        .group_by(ReitSnapshot.ticker)
        .subquery()
    )
    stmt = (
        select(ReitSnapshot)
        .join(
            subq,
            (ReitSnapshot.ticker == subq.c.ticker)
            & (ReitSnapshot.snapshot_date == subq.c.max_date),
        )
        .order_by(ReitSnapshot.ticker)
    )

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "ticker": r.ticker,
            "name": r.raw_json.get("name", r.ticker),
            "industrial": r.raw_json.get("industrial", "unknown"),
            "snapshot_date": r.snapshot_date.isoformat(),
            "price_sar": float(r.price_sar) if r.price_sar is not None else None,
            "nav_per_unit_sar": float(r.nav_per_unit_sar)
            if r.nav_per_unit_sar is not None
            else None,
            "nav_discount_pct": float(r.nav_discount_pct)
            if r.nav_discount_pct is not None
            else None,
            "distribution_per_unit_sar": float(r.distribution_per_unit_sar)
            if r.distribution_per_unit_sar is not None
            else None,
            "occupancy_pct": float(r.occupancy_pct) if r.occupancy_pct is not None else None,
        }
        for r in rows
    ]


# ── Listings aggregate ─────────────────────────────────────────────────────────


@router.get("/listings/aggregate")
async def aggregate_listings(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    listing_type: str | None = Query(None, description="sale or lease"),
    property_type: str | None = Query(None),
    city: str | None = Query(None),
) -> list[dict]:
    """Active listing stats aggregated by district x property_type.

    Returns: count, avg rent (SAR/yr), avg area (sqm), avg SAR/sqm/yr.
    Useful for building district price comparison charts.
    """
    from sqlalchemy import func

    stmt = (
        select(
            Listing.district,
            Listing.property_type,
            func.count().label("count"),
            func.avg(Listing.rent_sar_annual).label("avg_rent_sar_annual"),
            func.avg(Listing.area_sqm).label("avg_area_sqm"),
            func.avg(
                Listing.rent_sar_annual / Listing.area_sqm
            ).label("avg_rent_per_sqm"),
        )
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.district.isnot(None))
        .group_by(Listing.district, Listing.property_type)
        .order_by(func.avg(Listing.rent_sar_annual / Listing.area_sqm).desc().nulls_last())
    )

    if listing_type:
        stmt = stmt.where(Listing.listing_type == listing_type)
    if property_type:
        stmt = stmt.where(Listing.property_type == property_type)
    if city:
        stmt = stmt.where(Listing.city.ilike(f"%{city}%"))

    rows = (await session.execute(stmt)).all()
    return [
        {
            "district": r.district,
            "property_type": r.property_type,
            "count": r.count,
            "avg_rent_sar_annual": round(float(r.avg_rent_sar_annual), 0)
            if r.avg_rent_sar_annual is not None
            else None,
            "avg_area_sqm": round(float(r.avg_area_sqm), 0)
            if r.avg_area_sqm is not None
            else None,
            "avg_rent_per_sqm": round(float(r.avg_rent_per_sqm), 0)
            if r.avg_rent_per_sqm is not None
            else None,
        }
        for r in rows
    ]


# ── Transactions ───────────────────────────────────────────────────────────────


@router.get("/transactions")
async def list_transactions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    district: str | None = Query(None),
    property_type: str | None = Query(None),
    since: date | None = Query(None),
    until: date | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> list[dict]:
    """REGA transaction indicators. Filtered by district, property type, date range."""
    stmt = select(Transaction).order_by(desc(Transaction.transaction_date))
    if district:
        stmt = stmt.where(Transaction.district.ilike(f"%{district}%"))
    if property_type:
        stmt = stmt.where(Transaction.property_type == property_type)
    if since:
        stmt = stmt.where(Transaction.transaction_date >= since)
    if until:
        stmt = stmt.where(Transaction.transaction_date <= until)
    stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "transaction_date": r.transaction_date.isoformat(),
            "district": r.district,
            "district_id": r.district_id,
            "city": r.city,
            "property_type": r.property_type,
            "transaction_type": r.transaction_type,
            "area_sqm": float(r.area_sqm) if r.area_sqm is not None else None,
            "price_sar": float(r.price_sar),
            "source_priority": r.source_priority,
            "confidence": r.confidence,
            "source_id": r.source_id,
            "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
        }
        for r in rows
    ]


# ── Transaction aggregates (time-series) ───────────────────────────────────────


@router.get("/transactions/aggregate")
async def aggregate_transactions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    district: str | None = Query(None),
    property_type: str | None = Query(None),
    transaction_type: str | None = Query(None, description="sale or lease"),
    since: date | None = Query(None),
) -> list[dict]:
    """Monthly aggregated transaction metrics.

    Returns one row per month: total value, count, median price per sqm.
    Used by trend charts in the dashboard.
    """

    from sqlalchemy import func

    month_trunc = func.date_trunc("month", Transaction.transaction_date)

    stmt = (
        select(
            func.to_char(month_trunc, "YYYY-MM").label("month"),
            func.count().label("count"),
            func.sum(Transaction.price_sar).label("total_sar"),
            func.avg(Transaction.price_sar).label("avg_price_sar"),
        )
        .select_from(Transaction)
        .group_by(month_trunc)
        .order_by(month_trunc)
    )

    if district:
        stmt = stmt.where(Transaction.district.ilike(f"%{district}%"))
    if property_type:
        stmt = stmt.where(Transaction.property_type == property_type)
    if transaction_type:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)
    if since:
        stmt = stmt.where(Transaction.transaction_date >= since)

    rows = (await session.execute(stmt)).all()
    return [
        {
            "month": r.month,
            "count": r.count,
            "total_sar": float(r.total_sar) if r.total_sar is not None else 0.0,
            "avg_price_sar": round(float(r.avg_price_sar), 0)
            if r.avg_price_sar is not None
            else None,
        }
        for r in rows
    ]


# ── Listings ───────────────────────────────────────────────────────────────────


@router.get("/listings")
async def list_listings(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    portal: str | None = Query(None, description="e.g. aqar, bayut"),
    district: str | None = Query(None),
    listing_type: str | None = Query(None, description="sale or lease"),
    is_active: bool = Query(True),
    limit: int = Query(200, ge=1, le=2000),
) -> list[dict]:
    """Active warehouse/industrial listings from portals (Aqar, Bayut, etc.)."""
    stmt = select(Listing).order_by(desc(Listing.listed_at))
    if portal:
        stmt = stmt.where(Listing.portal == portal)
    if district:
        stmt = stmt.where(Listing.district.ilike(f"%{district}%"))
    if listing_type:
        stmt = stmt.where(Listing.listing_type == listing_type)
    stmt = stmt.where(Listing.is_active == is_active)
    stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "portal": r.portal,
            "external_id": r.external_id,
            "listing_type": r.listing_type,
            "property_type": r.property_type,
            "district": r.district,
            "city": r.city,
            "area_sqm": float(r.area_sqm) if r.area_sqm is not None else None,
            "price_sar": float(r.price_sar) if r.price_sar is not None else None,
            "rent_sar_annual": float(r.rent_sar_annual) if r.rent_sar_annual is not None else None,
            "listed_at": r.listed_at.isoformat() if r.listed_at else None,
            "is_active": r.is_active,
            "url": r.url,
        }
        for r in rows
    ]


# ── News ───────────────────────────────────────────────────────────────────────


@router.get("/news")
async def list_news(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    source: str | None = Query(None, description="e.g. argaam_en, modon"),
    since: date | None = Query(None),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0),
    q: str | None = Query(None, description="Keyword search in title_en and title_ar"),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    """News articles from Argaam, MODON, and other sources."""
    from sqlalchemy import or_

    stmt = select(NewsArticle).order_by(desc(NewsArticle.published_at))
    if source:
        stmt = stmt.where(NewsArticle.source == source)
    if since:
        stmt = stmt.where(NewsArticle.published_at >= since)  # type: ignore[arg-type]
    if min_relevance > 0:
        stmt = stmt.where(NewsArticle.relevance_score >= min_relevance)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                NewsArticle.title_en.ilike(pattern),
                NewsArticle.title_ar.ilike(pattern),
            )
        )
    stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "title_en": r.title_en,
            "title_ar": r.title_ar,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "relevance_score": float(r.relevance_score) if r.relevance_score is not None else None,
            "structured_facts": r.structured_facts,
        }
        for r in rows
    ]


# ── Transactions summary (grouped stats) ───────────────────────────────────────


@router.get("/transactions/summary")
async def transactions_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    since: date | None = Query(None, description="Start date for rolling window"),
) -> list[dict]:
    """Grouped transaction stats: per property_type x district, last 90 days default."""
    from datetime import timedelta

    from sqlalchemy import func

    if since is None:
        since = date.today() - timedelta(days=90)

    rows = (
        await session.execute(
            select(
                Transaction.property_type,
                Transaction.district,
                func.count().label("count"),
                func.sum(Transaction.price_sar).label("total_sar"),
                func.avg(Transaction.price_sar).label("avg_sar"),
                func.avg(Transaction.area_sqm).label("avg_sqm"),
            )
            .where(Transaction.transaction_date >= since)
            .group_by(Transaction.property_type, Transaction.district)
            .order_by(func.count().desc())
        )
    ).all()

    return [
        {
            "property_type": r.property_type,
            "district": r.district,
            "count": r.count,
            "total_sar": float(r.total_sar) if r.total_sar else None,
            "avg_sar": float(r.avg_sar) if r.avg_sar else None,
            "avg_sqm": float(r.avg_sqm) if r.avg_sqm else None,
            "avg_price_per_sqm": (
                float(r.avg_sar) / float(r.avg_sqm)
                if r.avg_sar and r.avg_sqm and float(r.avg_sqm) > 0
                else None
            ),
        }
        for r in rows
    ]


# ── News volume time-series ────────────────────────────────────────────────────


@router.get("/news/volume")
async def news_volume(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    weeks: int = Query(12, ge=1, le=52),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0),
) -> list[dict]:
    """Weekly article counts grouped by source.

    Returns one row per (week, source) pair with article count.
    Used to display news coverage trends over time.
    """
    from datetime import timedelta

    from sqlalchemy import func

    from app.models.market import NewsArticle

    since = date.today() - timedelta(weeks=weeks)
    week_trunc = func.date_trunc("week", NewsArticle.published_at)

    stmt = (
        select(
            func.to_char(week_trunc, "YYYY-MM-DD").label("week"),
            NewsArticle.source,
            func.count().label("count"),
        )
        .where(NewsArticle.published_at >= since)  # type: ignore[arg-type]
        .group_by(week_trunc, NewsArticle.source)
        .order_by(week_trunc, NewsArticle.source)
    )

    if min_relevance > 0:
        stmt = stmt.where(NewsArticle.relevance_score >= min_relevance)

    rows = (await session.execute(stmt)).all()
    return [
        {"week": r.week, "source": r.source, "count": r.count}
        for r in rows
    ]


# ── News article detail ────────────────────────────────────────────────────────


@router.get("/news/{article_id}")
async def get_news_article(
    article_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Single article with full body and structured facts."""
    from fastapi import HTTPException

    result = await session.execute(select(NewsArticle).where(NewsArticle.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    return {
        "id": article.id,
        "source": article.source,
        "external_id": article.external_id,
        "title_en": article.title_en,
        "title_ar": article.title_ar,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "relevance_score": float(article.relevance_score)
        if article.relevance_score is not None
        else None,
        "body_en": article.body_en,
        "body_ar": article.body_ar,
        "structured_facts": article.structured_facts,
        "model_id": article.model_id,
        "confidence": article.confidence,
        "extracted_at": article.extracted_at.isoformat() if article.extracted_at else None,
        "raw_uri": article.raw_uri,
    }


# ── Rent index ─────────────────────────────────────────────────────────────────


@router.get("/rent-index")
async def list_rent_index(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    district: str | None = Query(None),
    property_type: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict]:
    """Rent index observations from Knight Frank / CBRE / JLL reports and news."""
    stmt = select(RentIndex).order_by(desc(RentIndex.period), RentIndex.source_priority)
    if district:
        stmt = stmt.where(RentIndex.district.ilike(f"%{district}%"))
    if property_type:
        stmt = stmt.where(RentIndex.property_type == property_type)
    if source:
        stmt = stmt.where(RentIndex.source == source)
    stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "district": r.district,
            "city": r.city,
            "property_type": r.property_type,
            "period": r.period,
            "rent_sar_sqm_annual": float(r.rent_sar_sqm_annual) if r.rent_sar_sqm_annual else None,
            "yoy_change_pct": float(r.yoy_change_pct) if r.yoy_change_pct else None,
            "vacancy_pct": float(r.vacancy_pct) if r.vacancy_pct else None,
            "source": r.source,
            "source_priority": r.source_priority,
            "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
        }
        for r in rows
    ]


# ── Rent index summary (best observation per district/type) ────────────────────


@router.get("/rent-index/summary")
async def rent_index_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    property_type: str | None = Query(None),
) -> list[dict]:
    """Best (lowest priority number = most authoritative) rent index observation
    per district x property_type combination for the most recent period.

    Useful for building heatmaps and district-level comparison tables.
    """
    from sqlalchemy import func

    # Subquery: for each (district, property_type), get the most recent period
    # then pick the row with the lowest source_priority (most authoritative)
    recent_period_sq = (
        select(
            RentIndex.district,
            RentIndex.property_type,
            func.max(RentIndex.period).label("max_period"),
        )
        .group_by(RentIndex.district, RentIndex.property_type)
        .subquery()
    )

    best_priority_sq = (
        select(
            RentIndex.district,
            RentIndex.property_type,
            recent_period_sq.c.max_period,
            func.min(RentIndex.source_priority).label("min_priority"),
        )
        .join(
            recent_period_sq,
            (RentIndex.district == recent_period_sq.c.district)
            & (RentIndex.property_type == recent_period_sq.c.property_type)
            & (RentIndex.period == recent_period_sq.c.max_period),
        )
        .group_by(RentIndex.district, RentIndex.property_type, recent_period_sq.c.max_period)
        .subquery()
    )

    stmt = (
        select(RentIndex)
        .join(
            best_priority_sq,
            (RentIndex.district == best_priority_sq.c.district)
            & (RentIndex.property_type == best_priority_sq.c.property_type)
            & (RentIndex.period == best_priority_sq.c.max_period)
            & (RentIndex.source_priority == best_priority_sq.c.min_priority),
        )
        .order_by(RentIndex.district, RentIndex.property_type)
    )
    if property_type:
        stmt = stmt.where(RentIndex.property_type == property_type)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "district": r.district,
            "city": r.city,
            "property_type": r.property_type,
            "period": r.period,
            "rent_sar_sqm_annual": float(r.rent_sar_sqm_annual) if r.rent_sar_sqm_annual else None,
            "yoy_change_pct": float(r.yoy_change_pct) if r.yoy_change_pct else None,
            "vacancy_pct": float(r.vacancy_pct) if r.vacancy_pct else None,
            "source": r.source,
            "source_priority": r.source_priority,
        }
        for r in rows
    ]


# ── Tenders ────────────────────────────────────────────────────────────────────


@router.get("/tenders")
async def list_tenders(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    entity: str | None = Query(None, description="Filter by entity name (partial match)"),
    min_value: float | None = Query(None, description="Minimum tender value in SAR"),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """Active government tenders from Etimad relevant to industrial / warehouse sector."""
    stmt = select(Tender).order_by(desc(Tender.published_at)).limit(limit)
    if entity:
        stmt = stmt.where(Tender.entity_name.ilike(f"%{entity}%"))
    if min_value is not None:
        stmt = stmt.where(Tender.value_sar >= min_value)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "etimad_id": r.etimad_id,
            "entity_name": r.entity_name,
            "title_ar": r.title_ar,
            "title_en": r.title_en,
            "value_sar": float(r.value_sar) if r.value_sar is not None else None,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "deadline_at": r.deadline_at.isoformat() if r.deadline_at else None,
        }
        for r in rows
    ]


# ── CSV exports ────────────────────────────────────────────────────────────────


def _csv_stream(headers: list[str], rows: list[list[str]]) -> StreamingResponse:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
    )


@router.get("/transactions/export.csv")
async def export_transactions_csv(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    since: date | None = Query(None),
    until: date | None = Query(None),
    district: str | None = Query(None),
    property_type: str | None = Query(None),
) -> StreamingResponse:
    """Download REGA transactions as CSV (max 10,000 rows)."""
    stmt = select(Transaction).order_by(desc(Transaction.transaction_date)).limit(10_000)
    if district:
        stmt = stmt.where(Transaction.district.ilike(f"%{district}%"))
    if property_type:
        stmt = stmt.where(Transaction.property_type == property_type)
    if since:
        stmt = stmt.where(Transaction.transaction_date >= since)
    if until:
        stmt = stmt.where(Transaction.transaction_date <= until)

    rows = (await session.execute(stmt)).scalars().all()
    headers = [
        "id",
        "transaction_date",
        "district",
        "city",
        "property_type",
        "transaction_type",
        "area_sqm",
        "price_sar",
        "confidence",
    ]
    data = [
        [
            r.id,
            r.transaction_date.isoformat() if r.transaction_date else "",
            r.district or "",
            r.city or "",
            r.property_type or "",
            r.transaction_type or "",
            str(r.area_sqm) if r.area_sqm is not None else "",
            str(float(r.price_sar)) if r.price_sar is not None else "",
            str(r.confidence) if r.confidence is not None else "",
        ]
        for r in rows
    ]
    response = _csv_stream(headers, data)
    response.headers["Content-Disposition"] = "attachment; filename=transactions.csv"
    return response


@router.get("/listings/export.csv")
async def export_listings_csv(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    listing_type: str | None = Query(None),
    district: str | None = Query(None),
) -> StreamingResponse:
    """Download active warehouse/industrial listings as CSV (max 5,000 rows)."""
    stmt = (
        select(Listing)
        .where(Listing.is_active == True)  # noqa: E712
        .order_by(desc(Listing.listed_at))
        .limit(5_000)
    )
    if district:
        stmt = stmt.where(Listing.district.ilike(f"%{district}%"))
    if listing_type:
        stmt = stmt.where(Listing.listing_type == listing_type)

    rows = (await session.execute(stmt)).scalars().all()
    headers = [
        "id",
        "portal",
        "listing_type",
        "property_type",
        "district",
        "city",
        "area_sqm",
        "price_sar",
        "rent_sar_annual",
        "listed_at",
        "url",
    ]
    data = [
        [
            r.id,
            r.portal or "",
            r.listing_type or "",
            r.property_type or "",
            r.district or "",
            r.city or "",
            str(r.area_sqm) if r.area_sqm is not None else "",
            str(float(r.price_sar)) if r.price_sar is not None else "",
            str(float(r.rent_sar_annual)) if r.rent_sar_annual is not None else "",
            r.listed_at.isoformat() if r.listed_at else "",
            r.url or "",
        ]
        for r in rows
    ]
    response = _csv_stream(headers, data)
    response.headers["Content-Disposition"] = "attachment; filename=listings.csv"
    return response


@router.get("/tenders/export.csv")
async def export_tenders_csv(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    """Download Etimad tenders as CSV."""
    rows = (
        (await session.execute(select(Tender).order_by(desc(Tender.published_at)).limit(2_000)))
        .scalars()
        .all()
    )
    headers = [
        "id",
        "etimad_id",
        "entity_name",
        "title_ar",
        "title_en",
        "value_sar",
        "published_at",
        "deadline_at",
    ]
    data = [
        [
            r.id,
            r.etimad_id or "",
            r.entity_name or "",
            r.title_ar or "",
            r.title_en or "",
            str(float(r.value_sar)) if r.value_sar is not None else "",
            r.published_at.isoformat() if r.published_at else "",
            r.deadline_at.isoformat() if r.deadline_at else "",
        ]
        for r in rows
    ]
    response = _csv_stream(headers, data)
    response.headers["Content-Disposition"] = "attachment; filename=tenders.csv"
    return response


@router.get("/reit-snapshots/export.csv")
async def export_reit_csv(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ticker: str | None = Query(None),
) -> StreamingResponse:
    """Download REIT snapshots as CSV (latest 2,000 rows)."""
    stmt = (
        select(ReitSnapshot)
        .order_by(desc(ReitSnapshot.snapshot_date), ReitSnapshot.ticker)
        .limit(2_000)
    )
    if ticker:
        stmt = stmt.where(ReitSnapshot.ticker == ticker)

    rows = (await session.execute(stmt)).scalars().all()
    headers = [
        "ticker",
        "snapshot_date",
        "price_sar",
        "nav_per_unit_sar",
        "nav_discount_pct",
        "distribution_per_unit_sar",
        "occupancy_pct",
    ]
    data = [
        [
            r.ticker,
            r.snapshot_date.isoformat(),
            str(float(r.price_sar)) if r.price_sar is not None else "",
            str(float(r.nav_per_unit_sar)) if r.nav_per_unit_sar is not None else "",
            str(float(r.nav_discount_pct)) if r.nav_discount_pct is not None else "",
            str(float(r.distribution_per_unit_sar))
            if r.distribution_per_unit_sar is not None
            else "",
            str(float(r.occupancy_pct)) if r.occupancy_pct is not None else "",
        ]
        for r in rows
    ]
    response = _csv_stream(headers, data)
    response.headers["Content-Disposition"] = "attachment; filename=reit_snapshots.csv"
    return response


# ── Districts ──────────────────────────────────────────────────────────────────


@router.get("/districts")
async def list_districts(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    city: str | None = Query(None),
) -> list[dict]:
    """Canonical district registry — unique canonical_ids with their EN/AR names.

    Returns one entry per canonical district, with the English name preferred.
    Used for filter dropdowns and cross-source reconciliation.
    """

    stmt = (
        select(DistrictAlias)
        .where(DistrictAlias.source.is_(None))  # canonical rows have source=NULL
        .order_by(DistrictAlias.name_en)
    )
    if city:
        stmt = stmt.where(DistrictAlias.city.ilike(f"%{city}%"))

    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        # Fallback: distinct canonical_ids from any row
        sub = (
            select(
                DistrictAlias.canonical_id,
                DistrictAlias.name_en,
                DistrictAlias.name_ar,
                DistrictAlias.city,
            )
            .distinct(DistrictAlias.canonical_id)
            .order_by(DistrictAlias.canonical_id, DistrictAlias.name_en)
        )
        if city:
            sub = sub.where(DistrictAlias.city.ilike(f"%{city}%"))
        rows = (await session.execute(sub)).all()
        return [
            {
                "canonical_id": r.canonical_id,
                "name_en": r.name_en,
                "name_ar": r.name_ar,
                "city": r.city,
            }
            for r in rows
        ]

    return [
        {
            "canonical_id": r.canonical_id,
            "name_en": r.name_en,
            "name_ar": r.name_ar,
            "city": r.city,
        }
        for r in rows
    ]


# ── Summary stats ──────────────────────────────────────────────────────────────


# ── Primary market (Jawność cen mieszkań) ──────────────────────────────────────

_ACTIVE_STATUSES = "('active', 'wolne', 'w', 'free', 'available', 'a')"
# Warsaw residential PLN/m² sanity gate — excludes parsing failures from non-standard XLSX schemas
_PRICE_GUARD = "AND m2_price > 1000"

# Canonical 18 Warsaw dzielnice (lowercase, with diacritics as stored in DB)
_WARSAW_DZIELNICE_SQL = (
    "'śródmieście','wola','mokotów','ochota','żoliborz','bielany',"
    "'białołęka','targówek','praga-północ','praga-południe',"
    "'rembertów','wesoła','wawer','ursynów','wilanów','włochy','ursus','bemowo'"
)
_WARSAW_CITY_OR_DISTRICT = (
    f"(UPPER(TRIM({{t}}city)) = 'WARSZAWA' OR {{t}}district IN ({_WARSAW_DZIELNICE_SQL}))"
)

import re as _re

_DATASET_TITLE_PREFIXES = (
    "Ceny ofertowe mieszkań i domów dewelopera ",
    "Ceny ofertowe mieszkań dewelopera ",
    "Ceny ofertowe domów dewelopera ",
    "Ceny ofertowe lokali dewelopera ",
)
_DATASET_TITLE_SUFFIX_RE = _re.compile(
    r"(\s*-\s*inwestycja\b.*$"
    r"|\s+w\s+\d{4}\s+(i\s+\d{4}\s+)?r\.?\s*$"
    r"|\s+od\s+\d{4}.*$"
    r"|\s+\d{4}\s*r?\.\s*$"
    r"|\s*\.\s*$)",
    _re.IGNORECASE,
)


def _clean_dataset_title(raw: str) -> str:
    """Strip 'Ceny ofertowe mieszkań dewelopera' prefix and year/investment suffixes."""
    name = raw.strip()
    for prefix in _DATASET_TITLE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = _DATASET_TITLE_SUFFIX_RE.sub("", name).strip()
    return name or raw


@router.get("/primary-market/summary")
async def primary_market_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """KPI strip: Warsaw median PLN/m², active listings, feed lag, price move counts."""
    from sqlalchemy import text

    row = (
        await session.execute(
            text(f"""
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price) AS median_m2,
                    COUNT(*) AS active_units,
                    MAX(updated_at) AS last_updated,
                    EXTRACT(EPOCH FROM NOW() - MAX(updated_at))::int AS lag_seconds
                FROM primary_pricing
                WHERE LOWER(TRIM(status)) IN {_ACTIVE_STATUSES}
                  AND m2_price IS NOT NULL
                  {_PRICE_GUARD}
                  AND {_WARSAW_CITY_OR_DISTRICT.format(t="primary_pricing.")}
            """)
        )
    ).mappings().one_or_none()

    moves = (
        await session.execute(
            text(f"""
                SELECT
                    COUNT(*) FILTER (
                        WHERE (price_history -> -1 ->> 'm2_price')::numeric
                            > (price_history -> -2 ->> 'm2_price')::numeric
                    ) AS up_count,
                    COUNT(*) FILTER (
                        WHERE (price_history -> -1 ->> 'm2_price')::numeric
                            < (price_history -> -2 ->> 'm2_price')::numeric
                    ) AS dn_count
                FROM primary_pricing
                WHERE jsonb_array_length(price_history) >= 2
                  AND (price_history -> -1 ->> 'date')::date >= CURRENT_DATE - 7
                  AND (price_history -> -1 ->> 'm2_price')::numeric > 1000
                  AND (price_history -> -2 ->> 'm2_price')::numeric > 1000
                  AND (price_history -> -1 ->> 'm2_price')::numeric
                    IS DISTINCT FROM (price_history -> -2 ->> 'm2_price')::numeric
                  AND ABS(
                      (price_history -> -1 ->> 'm2_price')::numeric
                    - (price_history -> -2 ->> 'm2_price')::numeric
                  ) >= 50
                  AND ABS(
                      ((price_history -> -1 ->> 'm2_price')::numeric
                     - (price_history -> -2 ->> 'm2_price')::numeric)
                     / NULLIF((price_history -> -2 ->> 'm2_price')::numeric, 0) * 100
                  ) BETWEEN 0.1 AND 10
                  AND district IN ({_WARSAW_DZIELNICE_SQL})
            """)
        )
    ).mappings().one_or_none()

    if row is None:
        return {
            "median_m2": None, "active_units": 0, "last_updated": None,
            "feed_lag_seconds": None, "price_moves_7d": {"up": 0, "dn": 0},
        }

    return {
        "median_m2": round(float(row["median_m2"]), 0) if row["median_m2"] else None,
        "active_units": row["active_units"],
        "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
        "feed_lag_seconds": row["lag_seconds"],
        "price_moves_7d": {
            "up": moves["up_count"] if moves else 0,
            "dn": moves["dn_count"] if moves else 0,
        },
    }


@router.get("/primary-market/leaderboard")
async def primary_market_leaderboard(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """Per-firm: active investments, units, median PLN/m², primary districts."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(f"""
                WITH base AS (
                    SELECT
                        COALESCE(df.firm_name, jd.developer_name) AS firm_name,
                        COALESCE(df.firm_initials,
                            UPPER(LEFT(REGEXP_REPLACE(
                                COALESCE(df.firm_name, jd.developer_name, 'XX'), '[^A-Za-z]', '', 'g'
                            ), 2))
                        ) AS initials,
                        pp.developer_id,
                        pp.m2_price,
                        pp.district
                    FROM primary_pricing pp
                    JOIN jawnosc_developers jd ON jd.id = pp.developer_id
                    JOIN developer_firms df ON df.id = COALESCE(pp.firm_id, jd.firm_id)
                    WHERE LOWER(TRIM(pp.status)) IN {_ACTIVE_STATUSES}
                      AND pp.m2_price IS NOT NULL
                      {_PRICE_GUARD}
                      AND {_WARSAW_CITY_OR_DISTRICT.format(t="pp.")}
                )
                SELECT
                    firm_name,
                    initials,
                    COUNT(DISTINCT developer_id) AS investments,
                    COUNT(*) AS active_units,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price)) AS median_m2,
                    ARRAY_AGG(DISTINCT district ORDER BY district)
                        FILTER (WHERE district IS NOT NULL) AS districts
                FROM base
                GROUP BY firm_name, initials
                ORDER BY active_units DESC
                LIMIT 30
            """)
        )
    ).mappings().all()

    return [
        {
            "firm_name": r["firm_name"],
            "initials": r["initials"] or "?",
            "investments": r["investments"],
            "active_units": r["active_units"],
            "median_m2": int(r["median_m2"]) if r["median_m2"] else None,
            "districts": (r["districts"] or [])[:3],
        }
        for r in rows
    ]


@router.get("/primary-market/heatmap")
async def primary_market_heatmap(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """Median PLN/m² and unit count per Warsaw dzielnica."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(f"""
                SELECT
                    district,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price)) AS median_m2,
                    COUNT(*) AS unit_count
                FROM primary_pricing
                WHERE district IN ({_WARSAW_DZIELNICE_SQL})
                  AND LOWER(TRIM(status)) IN {_ACTIVE_STATUSES}
                  AND m2_price IS NOT NULL
                  {_PRICE_GUARD}
                GROUP BY district
                ORDER BY median_m2 DESC
            """)
        )
    ).mappings().all()

    return [
        {
            "district": r["district"],
            "median_m2": int(r["median_m2"]) if r["median_m2"] else None,
            "unit_count": r["unit_count"],
        }
        for r in rows
    ]


@router.get("/primary-market/price-changes")
async def primary_market_price_changes(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = Query(7, ge=1, le=90, description="Look-back window in days"),
) -> list[dict]:
    """Recent price change events extracted from price_history JSONB."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(f"""
                SELECT
                    df.firm_name AS matched_firm_name,
                    df.firm_initials AS matched_initials,
                    jd.developer_name AS raw_dataset_title,
                    pp.investment_name AS raw_investment_name,
                    pp.district,
                    (pp.price_history -> -1 ->> 'date')::date AS change_date,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY (pp.price_history -> -2 ->> 'm2_price')::numeric
                    )) AS prev_m2,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY (pp.price_history -> -1 ->> 'm2_price')::numeric
                    )) AS curr_m2,
                    COUNT(*) AS unit_count
                FROM primary_pricing pp
                JOIN jawnosc_developers jd ON jd.id = pp.developer_id
                LEFT JOIN developer_firms df ON df.id = COALESCE(pp.firm_id, jd.firm_id)
                WHERE jsonb_array_length(pp.price_history) >= 2
                  AND (pp.price_history -> -1 ->> 'm2_price')::numeric
                    IS DISTINCT FROM (pp.price_history -> -2 ->> 'm2_price')::numeric
                  AND (pp.price_history -> -1 ->> 'm2_price')::numeric > 1000
                  AND (pp.price_history -> -2 ->> 'm2_price')::numeric > 1000
                  AND (pp.price_history -> -1 ->> 'date')::date >= CURRENT_DATE - CAST(:days AS int)
                  AND pp.district IN ({_WARSAW_DZIELNICE_SQL})
                GROUP BY
                    df.firm_name,
                    df.firm_initials,
                    jd.developer_name,
                    pp.investment_name,
                    pp.district,
                    (pp.price_history -> -1 ->> 'date')::date
                ORDER BY change_date DESC, unit_count DESC
                LIMIT 200
            """),
            {"days": days},
        )
    ).mappings().all()

    result = []
    for r in rows:
        prev = float(r["prev_m2"]) if r["prev_m2"] else None
        curr = float(r["curr_m2"]) if r["curr_m2"] else None
        if not prev or not curr or prev == 0:
            continue
        dpct = round((curr - prev) / prev * 100, 2)
        abs_move = abs(curr - prev)
        # Sanity filters: ±10% cap, min 0.1% move, min 50 PLN/m² movement
        if abs(dpct) > 10 or abs(dpct) < 0.1 or abs_move < 50:
            continue

        # Developer display name: use matched firm_name if available, else clean dataset title
        raw_title = r["raw_dataset_title"] or ""
        if r["matched_firm_name"]:
            firm_display = r["matched_firm_name"]
            initials = r["matched_initials"] or firm_display[:2].upper()
        else:
            firm_display = _clean_dataset_title(raw_title)
            initials = (firm_display[:2].upper()) if firm_display else "??"

        # Investment name: use if it differs meaningfully from the cleaned developer name
        raw_inv = (r["raw_investment_name"] or "").strip()
        cleaned_title = _clean_dataset_title(raw_title)
        if raw_inv and raw_inv.lower() != cleaned_title.lower() and raw_inv.lower() != raw_title.lower():
            investment_display = raw_inv
        else:
            investment_display = cleaned_title

        result.append({
            "change_date": r["change_date"].isoformat() if r["change_date"] else None,
            "firm_name": firm_display,
            "initials": initials,
            "investment_name": investment_display,
            "district": r["district"],
            "prev_m2": int(prev),
            "curr_m2": int(curr),
            "dpct": dpct,
            "unit_count": r["unit_count"],
            "dir": "up" if dpct > 0 else "down",
        })
        if len(result) >= 50:
            break
    return result


@router.get("/primary-market/pipeline")
async def primary_market_pipeline(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """Active (non-sold) unit counts per Warsaw dzielnica — supply pipeline proxy."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(f"""
                SELECT
                    district,
                    COUNT(*) FILTER (
                        WHERE LOWER(TRIM(status)) IN ('active', 'wolne', 'w', 'free', 'available', 'a')
                    ) AS available_units,
                    COUNT(*) FILTER (
                        WHERE LOWER(TRIM(status)) IN ('reserved', 'zarezerwowane', 'z', 'rezerwacja')
                    ) AS reserved_units,
                    COUNT(*) AS total_units
                FROM primary_pricing
                WHERE district IN ({_WARSAW_DZIELNICE_SQL})
                  AND LOWER(TRIM(status)) NOT IN ('sold', 'sprzedane', 's')
                GROUP BY district
                ORDER BY total_units DESC
            """)
        )
    ).mappings().all()

    return [
        {
            "district": r["district"],
            "available_units": r["available_units"],
            "reserved_units": r["reserved_units"],
            "total_units": r["total_units"],
        }
        for r in rows
    ]


@router.get("/stats")
async def get_stats(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Row counts and freshness for all data tables — used by the dashboard header."""
    from sqlalchemy import func

    async def count(model):  # type: ignore[no-untyped-def]
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar() or 0

    return {
        "reit_snapshots": await count(ReitSnapshot),
        "transactions": await count(Transaction),
        "listings": await count(Listing),
        "news_articles": await count(NewsArticle),
        "rent_index": await count(RentIndex),
        "tenders": await count(Tender),
    }


# ── Intelligence feed (typed facts UNION) ─────────────────────────────────────

_FACT_TABLES: dict[str, tuple] = {
    "supply_events": (
        SupplyEvent,
        "COALESCE(event_type,'') || CASE WHEN developer IS NOT NULL THEN ' · ' || developer ELSE '' END || CASE WHEN location_description IS NOT NULL THEN ' · ' || location_description ELSE '' END",
    ),
    "regulatory_events": (
        RegulatoryEvent,
        "COALESCE(authority,'') || CASE WHEN summary IS NOT NULL THEN ' · ' || LEFT(summary,120) ELSE '' END",
    ),
    "macro_signals": (
        MacroSignal,
        "COALESCE(indicator,'') || CASE WHEN period IS NOT NULL THEN ' · ' || period ELSE '' END || CASE WHEN magnitude IS NOT NULL THEN ' · ' || magnitude ELSE '' END",
    ),
    "demand_signals": (
        DemandSignal,
        "COALESCE(sector,'') || CASE WHEN metric IS NOT NULL THEN ' · ' || metric ELSE '' END || CASE WHEN value IS NOT NULL THEN ' · ' || value ELSE '' END",
    ),
    "capital_markets_events": (
        CapitalMarketsEvent,
        "COALESCE(event_type,'') || CASE WHEN entity IS NOT NULL THEN ' · ' || entity ELSE '' END",
    ),
    "infrastructure_events": (
        InfrastructureEvent,
        "COALESCE(project,'') || CASE WHEN infra_type IS NOT NULL THEN ' · ' || infra_type ELSE '' END || CASE WHEN location IS NOT NULL THEN ' · ' || location ELSE '' END",
    ),
    "tenant_signals": (
        TenantSignal,
        "COALESCE(tenant_name,'') || CASE WHEN event_type IS NOT NULL THEN ' · ' || event_type ELSE '' END || CASE WHEN industry IS NOT NULL THEN ' · ' || industry ELSE '' END",
    ),
    "market_commentary": (
        MarketCommentary,
        "COALESCE(source_authority,'') || CASE WHEN topic IS NOT NULL THEN ' · ' || topic ELSE '' END",
    ),
}


@router.get("/intelligence/facts")
async def list_intelligence_facts(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    table: str | None = Query(None, description="Comma-separated table names; default=all"),
    min_confidence: int = Query(1, ge=1, le=5),
    since: date | None = Query(None),
    q: str | None = Query(None, description="Keyword search in source_citation"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Paginated unified feed of all typed facts across 8 signal tables.

    Returns: { total: int, items: [...] }
    Each item has: id, table, created_at, confidence, source_citation, article_id, summary
    """
    # Determine which tables to query
    requested = {t.strip() for t in table.split(",")} if table else set(_FACT_TABLES.keys())
    tables_to_query = [t for t in _FACT_TABLES if t in requested]
    if not tables_to_query:
        return {"total": 0, "items": []}

    conditions = []
    if min_confidence > 1:
        conditions.append(f"confidence >= {min_confidence}")
    if since:
        conditions.append(f"created_at >= '{since.isoformat()}'::date")
    if q:
        safe_q = q.replace("'", "''")
        conditions.append(f"source_citation ILIKE '%{safe_q}%'")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    branches = []
    for tbl_name, (_, summary_expr) in _FACT_TABLES.items():
        if tbl_name not in tables_to_query:
            continue
        branches.append(
            f"SELECT id, '{tbl_name}' AS table_name, created_at, confidence, "
            f"source_citation, article_id, ({summary_expr}) AS summary "
            f"FROM {tbl_name} {where_clause}"
        )

    union_sql = " UNION ALL ".join(branches)

    count_sql = text(f"SELECT COUNT(*) FROM ({union_sql}) AS t")
    total = (await session.execute(count_sql)).scalar() or 0

    page_sql = text(
        f"SELECT * FROM ({union_sql}) AS t "
        f"ORDER BY created_at DESC NULLS LAST "
        f"LIMIT {limit} OFFSET {offset}"
    )
    rows = (await session.execute(page_sql)).mappings().all()

    return {
        "total": int(total),
        "items": [
            {
                "id": r["id"],
                "table": r["table_name"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "confidence": r["confidence"],
                "source_citation": r["source_citation"],
                "article_id": r["article_id"],
                "summary": r["summary"],
            }
            for r in rows
        ],
    }
