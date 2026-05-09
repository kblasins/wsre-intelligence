"""Tests for the PDF structuring pipeline (promote_pdf_facts)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _make_outbox(facts: dict, source: str = "knight_frank") -> MagicMock:
    row = MagicMock()
    row.id = 1
    row.source = source
    row.raw_uri = "local://raw/test.pdf"
    row.scraper_meta = {
        "slug": "kf-ksa-2024",
        "extracted_facts": facts,
    }
    return row


class TestNormalizePtype:
    def test_warehouse_variants(self) -> None:
        from app.structuring.pdf import _normalize_ptype

        assert _normalize_ptype("warehouse") == "warehouse"
        assert _normalize_ptype("Warehouses") == "warehouse"
        assert _normalize_ptype("WAREHOUSE") == "warehouse"

    def test_industrial_land(self) -> None:
        from app.structuring.pdf import _normalize_ptype

        assert _normalize_ptype("industrial land") == "industrial_land"
        assert _normalize_ptype("industrial_land") == "industrial_land"

    def test_unknown_falls_back_to_warehouse(self) -> None:
        from app.structuring.pdf import _normalize_ptype

        assert _normalize_ptype("bizarre_type") == "warehouse"
        assert _normalize_ptype(None) == "warehouse"


class TestParsePeriod:
    def test_quarterly(self) -> None:
        from app.structuring.pdf import _parse_period

        assert _parse_period("Q4 2024") == "Q4 2024"
        assert _parse_period("Q1 2025") == "Q1 2025"

    def test_annual(self) -> None:
        from app.structuring.pdf import _parse_period

        assert _parse_period("2024") == "2024"

    def test_half_year(self) -> None:
        from app.structuring.pdf import _parse_period

        assert _parse_period("H2 2024") == "H2 2024"

    def test_none_returns_none(self) -> None:
        from app.structuring.pdf import _parse_period

        assert _parse_period(None) is None
        assert _parse_period("") is None


class TestPromotePdfFacts:
    @pytest.mark.asyncio
    async def test_upserts_rent_index_rows(self, db_session: AsyncSession) -> None:
        from app.structuring.pdf import promote_pdf_facts

        facts = {
            "rent_indices": [
                {
                    "district": "Industrial City",
                    "property_type": "warehouse",
                    "rent_sar_sqm_annual": 120.0,
                    "period": "Q4 2024",
                    "yoy_change_pct": 5.2,
                },
                {
                    "district": "North Riyadh",
                    "property_type": "logistics",
                    "rent_sar_sqm_annual": 95.0,
                    "period": "Q4 2024",
                    "yoy_change_pct": None,
                },
            ],
            "vacancy_rates": [],
        }
        outbox = _make_outbox(facts)
        count = await promote_pdf_facts(db_session, outbox)
        await db_session.commit()
        assert count == 2

    @pytest.mark.asyncio
    async def test_skips_rows_with_missing_period(self, db_session: AsyncSession) -> None:
        from app.structuring.pdf import promote_pdf_facts

        facts = {
            "rent_indices": [
                {
                    "district": "Olaya",
                    "property_type": "warehouse",
                    "rent_sar_sqm_annual": 110.0,
                    "period": None,
                },
                {
                    "district": "East",
                    "property_type": "warehouse",
                    "rent_sar_sqm_annual": 100.0,
                    "period": "Q3 2024",
                },
            ],
            "vacancy_rates": [],
        }
        outbox = _make_outbox(facts, source="cbre")
        count = await promote_pdf_facts(db_session, outbox)
        await db_session.commit()
        assert count == 1

    @pytest.mark.asyncio
    async def test_skips_implausible_rent(self, db_session: AsyncSession) -> None:
        from app.structuring.pdf import promote_pdf_facts

        facts = {
            "rent_indices": [
                # SAR 50,000/sqm/yr is clearly wrong
                {
                    "district": "North",
                    "property_type": "warehouse",
                    "rent_sar_sqm_annual": 50_000.0,
                    "period": "Q2 2024",
                },
                {
                    "district": "South",
                    "property_type": "warehouse",
                    "rent_sar_sqm_annual": 115.0,
                    "period": "Q2 2024",
                },
            ],
            "vacancy_rates": [],
        }
        outbox = _make_outbox(facts, source="jll")
        count = await promote_pdf_facts(db_session, outbox)
        await db_session.commit()
        assert count == 1

    @pytest.mark.asyncio
    async def test_no_facts_returns_zero(self, db_session: AsyncSession) -> None:
        from app.structuring.pdf import promote_pdf_facts

        outbox = _make_outbox({})
        count = await promote_pdf_facts(db_session, outbox)
        assert count == 0

    @pytest.mark.asyncio
    async def test_vacancy_rates_promoted(self, db_session: AsyncSession) -> None:
        from app.structuring.pdf import promote_pdf_facts

        facts = {
            "rent_indices": [],
            "vacancy_rates": [
                {
                    "district": "Industrial City",
                    "property_type": "warehouse",
                    "vacancy_pct": 8.5,
                    "period": "Q4 2024",
                },
            ],
        }
        outbox = _make_outbox(facts, source="cbre")
        count = await promote_pdf_facts(db_session, outbox)
        await db_session.commit()
        assert count == 1
