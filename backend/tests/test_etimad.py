"""Tests for the Etimad tender scraper and extractor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── extract_from_blob ──────────────────────────────────────────────────────────


class TestExtractFromBlob:
    """extract_from_blob should upsert Tender rows from a stored JSON blob."""

    @pytest.mark.asyncio
    async def test_extracts_full_item(self, db_session: AsyncSession) -> None:
        from sqlalchemy import select

        from app.ingestion.scrapers.etimad import extract_from_blob
        from app.models.ingestion import RawIngestOutbox
        from app.models.market import Tender

        outbox = RawIngestOutbox(
            source="etimad",
            raw_uri="local://test/etimad/page1.json",
            content_sha1="a" * 40,
            content_type="application/json",
            structured=0,
            scraper_meta={},
        )
        db_session.add(outbox)
        await db_session.commit()
        await db_session.refresh(outbox)

        payload = {
            "items": [
                {
                    "tenderIdString": "TND-2026-001",
                    "agencyName": "MODON",
                    "tenderName": "إنشاء مستودع صناعي",
                    "tenderNameEn": "Industrial Warehouse Construction",
                    "tenderValue": 15_000_000,
                    "publishDate": "2026-03-01T00:00:00Z",
                    "lastOfferDate": "2026-04-30T23:59:00Z",
                }
            ]
        }
        raw = json.dumps(payload).encode()

        await extract_from_blob(db_session, raw, outbox)

        result = await db_session.execute(select(Tender).where(Tender.etimad_id == "TND-2026-001"))
        tender = result.scalar_one_or_none()
        assert tender is not None
        assert tender.entity_name == "MODON"
        assert tender.title_en == "Industrial Warehouse Construction"
        assert tender.title_ar == "إنشاء مستودع صناعي"
        assert float(tender.value_sar) == 15_000_000.0
        assert tender.published_at is not None
        assert tender.deadline_at is not None

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db_session: AsyncSession) -> None:
        from sqlalchemy import select

        from app.ingestion.scrapers.etimad import extract_from_blob
        from app.models.ingestion import RawIngestOutbox
        from app.models.market import Tender

        # Pre-seed an existing tender
        db_session.add(
            Tender(
                etimad_id="TND-UPSERT-001",
                entity_name="Old Entity",
                title_ar="عنوان قديم",
                value_sar=1_000_000,
                raw_json={},
            )
        )
        await db_session.commit()

        outbox = RawIngestOutbox(
            source="etimad",
            raw_uri="local://test/etimad/upd.json",
            content_sha1="b" * 40,
            content_type="application/json",
            structured=0,
            scraper_meta={},
        )
        db_session.add(outbox)
        await db_session.commit()
        await db_session.refresh(outbox)

        payload = {
            "items": [
                {
                    "tenderIdString": "TND-UPSERT-001",
                    "agencyName": "MODON Updated",
                    "tenderName": "عنوان محدّث",
                    "tenderValue": 2_000_000,
                }
            ]
        }
        await extract_from_blob(db_session, json.dumps(payload).encode(), outbox)

        result = await db_session.execute(
            select(Tender).where(Tender.etimad_id == "TND-UPSERT-001")
        )
        tender = result.scalar_one()
        assert tender.entity_name == "MODON Updated"
        assert float(tender.value_sar) == 2_000_000.0

    @pytest.mark.asyncio
    async def test_handles_empty_items(self, db_session: AsyncSession) -> None:
        from app.ingestion.scrapers.etimad import extract_from_blob
        from app.models.ingestion import RawIngestOutbox

        outbox = RawIngestOutbox(
            source="etimad",
            raw_uri="local://test/etimad/empty.json",
            content_sha1="c" * 40,
            content_type="application/json",
            structured=0,
            scraper_meta={},
        )
        db_session.add(outbox)
        await db_session.commit()
        await db_session.refresh(outbox)

        payload = {"items": []}
        await extract_from_blob(db_session, json.dumps(payload).encode(), outbox)
        # No error expected

    @pytest.mark.asyncio
    async def test_fallback_id_from_hash(self, db_session: AsyncSession) -> None:
        """When no id field is present, a SHA-1-derived ID is used."""
        from sqlalchemy import select

        from app.ingestion.scrapers.etimad import extract_from_blob
        from app.models.ingestion import RawIngestOutbox
        from app.models.market import Tender

        outbox = RawIngestOutbox(
            source="etimad",
            raw_uri="local://test/etimad/hash.json",
            content_sha1="d" * 40,
            content_type="application/json",
            structured=0,
            scraper_meta={},
        )
        db_session.add(outbox)
        await db_session.commit()
        await db_session.refresh(outbox)

        # Item has no id fields
        payload = {"items": [{"agencyName": "Test", "tenderName": "Test Tender"}]}
        await extract_from_blob(db_session, json.dumps(payload).encode(), outbox)

        result = await db_session.execute(select(Tender))
        rows = result.scalars().all()
        assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_missing_value_field_accepted(self, db_session: AsyncSession) -> None:
        """Items without a value_sar are accepted with value_sar = null."""
        from sqlalchemy import select

        from app.ingestion.scrapers.etimad import extract_from_blob
        from app.models.ingestion import RawIngestOutbox
        from app.models.market import Tender

        outbox = RawIngestOutbox(
            source="etimad",
            raw_uri="local://test/etimad/novalue.json",
            content_sha1="e" * 40,
            content_type="application/json",
            structured=0,
            scraper_meta={},
        )
        db_session.add(outbox)
        await db_session.commit()
        await db_session.refresh(outbox)

        payload = {"items": [{"tenderIdString": "TND-NOVALUE", "agencyName": "Test"}]}
        await extract_from_blob(db_session, json.dumps(payload).encode(), outbox)

        result = await db_session.execute(select(Tender).where(Tender.etimad_id == "TND-NOVALUE"))
        tender = result.scalar_one()
        assert tender.value_sar is None


# ── reconciler recognises etimad source ────────────────────────────────────────


class TestReconcilerEtimad:
    def test_etimad_source_resolves(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        fn = _get_extractor("etimad")
        assert fn is not None
        assert callable(fn)


# ── TendersPanel API ────────────────────────────────────────────────────────────


class TestTendersApi:
    @pytest.mark.asyncio
    async def test_tenders_returns_list(self, api_client) -> None:  # type: ignore[no-untyped-def]
        """Endpoint must return 200 with a list (may be empty or populated from other tests)."""
        resp = await api_client.get("/api/tenders")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_tenders_returns_data(self, api_client, db_session: AsyncSession) -> None:  # type: ignore[no-untyped-def]
        from app.models.market import Tender

        db_session.add(
            Tender(
                etimad_id="API-TEST-001",
                entity_name="MODON",
                title_ar="مستودع",
                title_en="Warehouse",
                value_sar=5_000_000,
                published_at=datetime(2026, 3, 1, tzinfo=UTC),
                raw_json={},
            )
        )
        await db_session.commit()

        resp = await api_client.get("/api/tenders")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        row = next(r for r in data if r["etimad_id"] == "API-TEST-001")
        assert row["entity_name"] == "MODON"
        assert row["value_sar"] == 5_000_000.0

    @pytest.mark.asyncio
    async def test_tenders_value_filter(self, api_client, db_session: AsyncSession) -> None:  # type: ignore[no-untyped-def]
        from app.models.market import Tender

        db_session.add_all(
            [
                Tender(etimad_id="SMALL-001", title_ar="صغير", value_sar=100_000, raw_json={}),
                Tender(etimad_id="BIG-001", title_ar="كبير", value_sar=50_000_000, raw_json={}),
            ]
        )
        await db_session.commit()

        resp = await api_client.get("/api/tenders?min_value=1000000")
        assert resp.status_code == 200
        ids = [r["etimad_id"] for r in resp.json()]
        assert "BIG-001" in ids
        assert "SMALL-001" not in ids
