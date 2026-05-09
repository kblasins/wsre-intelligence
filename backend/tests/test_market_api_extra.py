"""Tests for additional market API endpoints: news detail, rent-index summary, districts, CSV."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


# ── GET /api/news/{id} ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_news_detail_404_on_missing(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/news/999999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rent_index_summary_returns_list(api_client: AsyncClient) -> None:
    """Summary endpoint returns a list (may contain rows seeded by other tests)."""
    resp = await api_client.get("/api/rent-index/summary")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_rent_index_summary_filters_by_type(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/rent-index/summary?property_type=warehouse")
    assert resp.status_code == 200
    data = resp.json()
    for row in data:
        assert row["property_type"] == "warehouse"


@pytest.mark.asyncio
async def test_news_endpoint_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/news?limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_rent_index_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/rent-index?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── PATCH /api/admin/review-queue/{id} ───────────────────────────────────────


@pytest.mark.asyncio
async def test_review_queue_patch_404_on_missing(api_client: AsyncClient) -> None:
    resp = await api_client.patch("/api/admin/review-queue/999999")
    assert resp.status_code == 404


# ── GET /api/news?q= (server-side search) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_news_search_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/news?q=warehouse")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_news_search_matches_title(api_client: AsyncClient, db_session) -> None:
    from datetime import UTC, datetime

    from app.models.market import NewsArticle

    article = NewsArticle(
        source="argaam_en",
        external_id="search-test-warehouse-001",
        title_en="Riyadh warehouse demand surges in Q2 2025",
        url="https://example.com/warehouse-article",
        published_at=datetime.now(UTC),
        raw_uri="local://test",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(article)
    await db_session.commit()

    resp = await api_client.get("/api/news?q=warehouse+demand&limit=50")
    assert resp.status_code == 200
    titles = [a["title_en"] for a in resp.json() if a["title_en"]]
    assert any("warehouse" in (t or "").lower() for t in titles)


@pytest.mark.asyncio
async def test_news_search_no_match_returns_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/news?q=xyzzy_no_such_keyword_12345")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_news_search_arabic_title(api_client: AsyncClient, db_session) -> None:
    from datetime import UTC, datetime

    from app.models.market import NewsArticle

    article = NewsArticle(
        source="argaam_ar",
        external_id="search-test-ar-001",
        title_ar="السوق العقاري في الرياض",
        url="https://example.com/ar-article",
        published_at=datetime.now(UTC),
        raw_uri="local://test",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(article)
    await db_session.commit()

    resp = await api_client.get("/api/news?q=الرياض&limit=50")
    assert resp.status_code == 200
    results = resp.json()
    assert any(a["title_ar"] and "الرياض" in a["title_ar"] for a in results)


# ── CSV export endpoints ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transactions_csv_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/transactions/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().splitlines()
    # Header only when empty
    assert len(lines) == 1
    assert "transaction_date" in lines[0]


@pytest.mark.asyncio
async def test_transactions_csv_with_data(api_client: AsyncClient, db_session) -> None:
    from datetime import UTC, date, datetime

    from app.models.market import Transaction

    tx = Transaction(
        transaction_date=date(2025, 3, 1),
        district="Al Kharj",
        city="Riyadh",
        property_type="warehouse",
        transaction_type="sale",
        price_sar=4_500_000,
        area_sqm=1200,
        source_priority=1,
        confidence=3,
        extracted_at=datetime.now(UTC),
    )
    db_session.add(tx)
    await db_session.commit()

    resp = await api_client.get("/api/transactions/export.csv")
    assert resp.status_code == 200
    text = resp.text
    assert "Al Kharj" in text
    assert "warehouse" in text
    lines = text.strip().splitlines()
    assert len(lines) >= 2  # header + at least one row


@pytest.mark.asyncio
async def test_listings_csv_headers(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/listings/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    header = resp.text.splitlines()[0]
    for col in ["portal", "listing_type", "area_sqm", "rent_sar_annual"]:
        assert col in header


@pytest.mark.asyncio
async def test_listings_csv_only_active(api_client: AsyncClient, db_session) -> None:
    from datetime import UTC, datetime

    from app.models.market import Listing

    active = Listing(
        portal="aqar",
        external_id="csv-test-active-1",
        listing_type="lease",
        property_type="warehouse",
        district="Riyadh Industrial City",
        city="Riyadh",
        is_active=True,
        listed_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    inactive = Listing(
        portal="aqar",
        external_id="csv-test-inactive-1",
        listing_type="lease",
        property_type="warehouse",
        district="Riyadh Industrial City",
        city="Riyadh",
        is_active=False,
        listed_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    db_session.add_all([active, inactive])
    await db_session.commit()

    resp = await api_client.get("/api/listings/export.csv")
    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    # inactive row should not appear — count only data rows
    ids_in_csv = [line.split(",")[0] for line in lines[1:]]
    assert str(inactive.id) not in ids_in_csv


@pytest.mark.asyncio
async def test_tenders_csv_headers(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/tenders/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    header = resp.text.splitlines()[0]
    for col in ["etimad_id", "entity_name", "value_sar", "deadline_at"]:
        assert col in header


@pytest.mark.asyncio
async def test_tenders_csv_with_data(api_client: AsyncClient, db_session) -> None:
    from datetime import UTC, date, datetime

    from app.models.market import Tender

    tender = Tender(
        etimad_id="csv-etm-001",
        entity_name="Ministry of Industry",
        title_ar="مشروع مستودعات",
        title_en="Warehouse Construction Project",
        value_sar=12_000_000,
        published_at=datetime.now(UTC),
        deadline_at=date(2025, 9, 30),
    )
    db_session.add(tender)
    await db_session.commit()

    resp = await api_client.get("/api/tenders/export.csv")
    assert resp.status_code == 200
    assert "Ministry of Industry" in resp.text
    assert "csv-etm-001" in resp.text


# ── GET /api/districts ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_districts_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/districts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_districts_with_data(api_client: AsyncClient, db_session) -> None:
    from app.models.market import DistrictAlias

    alias = DistrictAlias(
        canonical_id=1001,
        alias="Second Industrial City",
        alias_lang="en",
        name_en="Second Industrial City",
        name_ar="المدينة الصناعية الثانية",
        city="Riyadh",
        source=None,  # canonical row
    )
    db_session.add(alias)
    await db_session.commit()

    resp = await api_client.get("/api/districts")
    assert resp.status_code == 200
    data = resp.json()
    assert any(d["name_en"] == "Second Industrial City" for d in data)


@pytest.mark.asyncio
async def test_districts_city_filter(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/districts?city=Riyadh")
    assert resp.status_code == 200
    data = resp.json()
    for d in data:
        assert d["city"] is not None


# ── GET /api/transactions/aggregate ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_transaction_aggregate_empty_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/transactions/aggregate")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_transaction_aggregate_with_data(api_client: AsyncClient, db_session) -> None:
    """Seeded transaction appears in monthly aggregate."""
    from datetime import date, datetime

    from app.models.market import Transaction

    tx = Transaction(
        transaction_date=date(2025, 3, 15),
        district="Al Kharj",
        city="Riyadh",
        property_type="warehouse",
        transaction_type="sale",
        area_sqm=1000,
        price_sar=5_000_000,
        source_id="agg-test-001",
        source_priority=1,
        extracted_at=datetime.now(UTC),
    )
    db_session.add(tx)
    await db_session.commit()

    resp = await api_client.get(
        "/api/transactions/aggregate?property_type=warehouse&district=Al+Kharj"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    row = next((r for r in data if r["month"] == "2025-03"), None)
    assert row is not None
    assert row["count"] >= 1
    assert row["total_sar"] >= 5_000_000
    assert set(row.keys()) == {"month", "count", "total_sar", "avg_price_sar"}


# ── GET /api/news/volume ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_news_volume_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/news/volume?weeks=4")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_news_volume_with_data(api_client: AsyncClient, db_session) -> None:
    """Seeded article appears in weekly volume counts."""
    from datetime import UTC, datetime

    from app.models.market import NewsArticle

    article = NewsArticle(
        source="modon",
        external_id="vol-test-001",
        title_en="MODON announces new industrial zone",
        url="https://example.com/modon-article",
        published_at=datetime.now(UTC),
        raw_uri="local://test",
        extracted_at=datetime.now(UTC),
        relevance_score=0.9,
    )
    db_session.add(article)
    await db_session.commit()

    resp = await api_client.get("/api/news/volume?weeks=4")
    assert resp.status_code == 200
    data = resp.json()
    modon_rows = [r for r in data if r["source"] == "modon"]
    assert len(modon_rows) >= 1
    assert all(r["count"] >= 1 for r in modon_rows)
    assert all(set(r.keys()) == {"week", "source", "count"} for r in modon_rows)


# ── GET /api/listings/aggregate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_listings_aggregate_empty_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/listings/aggregate")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_listings_aggregate_with_data(api_client: AsyncClient, db_session) -> None:
    """Seeded active lease listing appears in aggregate by district."""
    from datetime import UTC, datetime

    from app.models.market import Listing

    listing = Listing(
        portal="aqar",
        external_id="agg-listing-test-001",
        listing_type="lease",
        property_type="warehouse",
        district="King Abdullah Economic City",
        city="Jeddah",
        area_sqm=2000,
        rent_sar_annual=300_000,
        is_active=True,
        listed_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    db_session.add(listing)
    await db_session.commit()

    resp = await api_client.get(
        "/api/listings/aggregate?listing_type=lease&property_type=warehouse"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    row = next((r for r in data if r["district"] == "King Abdullah Economic City"), None)
    assert row is not None
    assert row["count"] >= 1
    assert set(row.keys()) == {
        "district", "property_type", "count",
        "avg_rent_sar_annual", "avg_area_sqm", "avg_rent_per_sqm",
    }
    assert row["avg_rent_per_sqm"] is not None
    assert row["avg_rent_per_sqm"] > 0


@pytest.mark.asyncio
async def test_listings_aggregate_filters_inactive(api_client: AsyncClient, db_session) -> None:
    """Inactive listings must not appear in aggregate."""
    from datetime import UTC, datetime

    from app.models.market import Listing

    inactive = Listing(
        portal="bayut",
        external_id="agg-listing-inactive-001",
        listing_type="lease",
        property_type="factory",
        district="Jeddah Industrial City",
        city="Jeddah",
        area_sqm=500,
        rent_sar_annual=50_000,
        is_active=False,
        listed_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    db_session.add(inactive)
    await db_session.commit()

    resp = await api_client.get(
        "/api/listings/aggregate?property_type=factory"
    )
    assert resp.status_code == 200
    data = resp.json()
    # The inactive listing's district+type pair should NOT appear
    match = next(
        (r for r in data if r["district"] == "Jeddah Industrial City" and r["property_type"] == "factory"),
        None,
    )
    assert match is None
