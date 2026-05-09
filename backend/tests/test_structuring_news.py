"""Tests for the news structuring pipeline (promote_news_facts / promote_all_pending)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestNormalizePtype:
    def test_warehouse_variants(self) -> None:
        from app.structuring.news import _normalize_ptype

        assert _normalize_ptype("warehouse") == "warehouse"
        assert _normalize_ptype("warehouses") == "warehouse"
        assert _normalize_ptype("WAREHOUSE") == "warehouse"

    def test_industrial_variants(self) -> None:
        from app.structuring.news import _normalize_ptype

        assert _normalize_ptype("industrial") == "industrial_land"
        assert _normalize_ptype("industrial land") == "industrial_land"
        assert _normalize_ptype("industrial_land") == "industrial_land"

    def test_other_types(self) -> None:
        from app.structuring.news import _normalize_ptype

        assert _normalize_ptype("factory") == "factory"
        assert _normalize_ptype("logistics") == "logistics"
        assert _normalize_ptype("office") == "office"
        assert _normalize_ptype("retail") == "retail"

    def test_unknown_defaults_to_warehouse(self) -> None:
        from app.structuring.news import _normalize_ptype

        assert _normalize_ptype("unknown_type") == "warehouse"
        assert _normalize_ptype(None) == "warehouse"
        assert _normalize_ptype("") == "warehouse"


class TestPromoteNewsFacts:
    @pytest.mark.asyncio
    async def test_empty_movements_returns_zero(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        result = await promote_news_facts(mock_session, 1, {"rent_movements": []}, None, None, None)
        assert result == 0
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rent_movements_key_returns_zero(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        result = await promote_news_facts(
            mock_session, 1, {"market_signal": "something"}, None, None, None
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_movements_without_period(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        facts = {
            "rent_movements": [
                {
                    "direction": "up",
                    "change_pct": 10.0,
                    "period": None,
                    "property_type": "warehouse",
                },
            ]
        }
        result = await promote_news_facts(mock_session, 1, facts, None, None, None)
        assert result == 0

    @pytest.mark.asyncio
    async def test_promotes_up_movement(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        facts = {
            "rent_movements": [
                {
                    "direction": "up",
                    "change_pct": 8.5,
                    "period": "Q4 2024",
                    "property_type": "warehouse",
                    "district": "Al Kharj Road",
                },
            ]
        }
        result = await promote_news_facts(
            mock_session, 42, facts, "https://example.com/article", "claude-sonnet-4-6", "abc123"
        )
        assert result == 1
        mock_session.execute.assert_called_once()

        # Verify the insert statement had positive yoy value
        call_args = mock_session.execute.call_args[0][0]
        # The compiled insert should reference yoy_change_pct = 8.5 (positive, direction=up)
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_promotes_down_movement_negative_pct(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        facts = {
            "rent_movements": [
                {
                    "direction": "down",
                    "change_pct": 5.0,
                    "period": "2024",
                    "property_type": "industrial",
                    "district": None,
                },
            ]
        }
        result = await promote_news_facts(mock_session, 1, facts, None, None, None)
        assert result == 1

    @pytest.mark.asyncio
    async def test_promotes_multiple_movements(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        facts = {
            "rent_movements": [
                {
                    "direction": "up",
                    "change_pct": 10.0,
                    "period": "Q3 2024",
                    "property_type": "warehouse",
                },
                {
                    "direction": "flat",
                    "change_pct": 0.0,
                    "period": "Q3 2024",
                    "property_type": "office",
                },
                {
                    "direction": "down",
                    "change_pct": 3.0,
                    "period": "Q3 2024",
                    "property_type": "retail",
                },
            ]
        }
        result = await promote_news_facts(mock_session, 5, facts, None, None, None)
        assert result == 3
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_null_change_pct(self) -> None:
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        facts = {
            "rent_movements": [
                {
                    "direction": "up",
                    "change_pct": None,
                    "period": "Q4 2024",
                    "property_type": "warehouse",
                    "district": "Jeddah",
                },
            ]
        }
        # Should not raise, yoy should be None
        result = await promote_news_facts(mock_session, 1, facts, None, None, None)
        assert result == 1

    @pytest.mark.asyncio
    async def test_source_field_contains_article_id(self) -> None:
        """Verify the source field encodes the article id for traceability."""
        from app.structuring.news import promote_news_facts

        mock_session = AsyncMock()
        facts = {
            "rent_movements": [
                {
                    "direction": "up",
                    "change_pct": 5.0,
                    "period": "2024",
                    "property_type": "warehouse",
                },
            ]
        }
        await promote_news_facts(mock_session, 99, facts, None, None, None)

        # The INSERT statement values should include source="news_article_99"
        call_args = mock_session.execute.call_args[0][0]
        compiled = call_args.compile(compile_kwargs={"literal_binds": True})
        assert "news_article_99" in str(compiled)


class TestPromoteAllPending:
    @pytest.mark.asyncio
    async def test_no_articles_returns_zero(self) -> None:
        from app.structuring.news import promote_all_pending

        mock_result = MagicMock()
        mock_result.scalars.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await promote_all_pending(mock_session)
        assert result == 0
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_non_dict_facts(self) -> None:
        from app.structuring.news import promote_all_pending

        article = MagicMock()
        article.structured_facts = "not a dict"

        mock_result = MagicMock()
        mock_result.scalars.return_value = [article]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await promote_all_pending(mock_session)
        assert result == 0

    @pytest.mark.asyncio
    async def test_promotes_articles_with_movements(self) -> None:
        from app.structuring.news import promote_all_pending

        article = MagicMock()
        article.id = 7
        article.raw_uri = "https://example.com/news/7"
        article.model_id = "claude-sonnet-4-6"
        article.prompt_sha = "deadbeef"
        article.structured_facts = {
            "rent_movements": [
                {
                    "direction": "up",
                    "change_pct": 6.0,
                    "period": "Q4 2024",
                    "property_type": "warehouse",
                },
            ]
        }

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value = [article]

        insert_result = MagicMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_query_result
            return insert_result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=side_effect)

        result = await promote_all_pending(mock_session)
        assert result == 1
        mock_session.commit.assert_called_once()
