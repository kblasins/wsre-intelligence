"""Tests for the news article body fetcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExtractBody:
    def test_source_specific_selector_used_first(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        # Content must exceed 200 chars to pass the "real content" threshold
        body = (
            "This is the article text about Riyadh warehouses and industrial real estate "
            "in the Kingdom of Saudi Arabia. Warehouse rents in the Al Kharj Road corridor "
            "have risen by 8% year-on-year driven by logistics demand from e-commerce operators."
        )
        html = f'<html><body><div class="article-content">{body}</div></body></html>'
        result = _extract_body(html, "argaam_en")
        assert "article text" in result
        assert len(result) > 50

    def test_fallback_to_default_selectors(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        html = """<html><body>
            <article>
                <p>Main article content about warehouse rents in Riyadh industrial zones.</p>
                <p>Additional information about MODON cities and logistics supply.</p>
            </article>
        </body></html>"""
        result = _extract_body(html, "unknown_source")
        assert "warehouse" in result or "MODON" in result

    def test_fallback_to_p_tags(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        # No article tag, no class matches — should fall back to all <p> tags
        html = """<html><body>
            <div class="wrapper">
                <p>First paragraph with substantial content about real estate.</p>
                <p>Second paragraph discussing warehouse rents and transactions.</p>
                <p>Third paragraph about industrial land prices in Riyadh.</p>
            </div>
        </body></html>"""
        result = _extract_body(html, "unknown_source")
        assert "paragraph" in result

    def test_short_content_skipped(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        # Content shorter than 200 chars should not match the selector threshold
        html = """<html><body>
            <div class="article-content">Short.</div>
            <p>Long enough paragraph with a lot of content about Saudi Arabia industrial real estate markets and warehouse rental rates.</p>
        </body></html>"""
        result = _extract_body(html, "argaam_en")
        # Falls through to p tags since article-content too short
        assert len(result) > 0

    def test_body_capped_at_8000_chars(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        long_text = "x" * 200  # definitely > 200 chars per selector match
        html = f"<html><body><article>{'<p>' + long_text + '</p>' * 100}</article></body></html>"
        result = _extract_body(html, "argaam_en")
        assert len(result) <= 8000

    def test_modon_selectors(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        html = """<html><body>
            <div class="ms-rtestate-field">
                MODON Industrial Cities Authority announces new logistics hub in Jeddah.
                The facility spans 50,000 sqm and will house 200 warehouse units for
                small and medium enterprises in the Kingdom of Saudi Arabia.
            </div>
        </body></html>"""
        result = _extract_body(html, "modon")
        assert "MODON" in result or "warehouse" in result

    def test_empty_html_returns_empty_string(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        result = _extract_body("<html><body></body></html>", "argaam_en")
        assert result == ""

    def test_ar_source_uses_same_selectors(self) -> None:
        from app.ingestion.scrapers.news_body import _extract_body

        # Content must exceed 200 chars — repeat Arabic text to ensure threshold is met
        body = (
            "مقال عن أسواق العقارات الصناعية في الرياض ومستودعات اللوجستيات وأسعار الإيجار "
            "في المناطق الصناعية بالمملكة العربية السعودية وتأثير ذلك على صناديق الاستثمار "
            "العقاري المدرجة في السوق السعودية والطلب المتنامي من شركات التجارة الإلكترونية."
        )
        html = f'<html><body><div class="article-content">{body}</div></body></html>'
        result = _extract_body(html, "argaam_ar")
        assert len(result) > 50


class TestFetchBody:
    @pytest.mark.asyncio
    async def test_returns_none_for_no_url(self) -> None:
        from app.ingestion.scrapers.news_body import _fetch_body

        article = MagicMock()
        article.url = None

        async with __import__("httpx").AsyncClient() as client:
            result = await _fetch_body(client, article)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self) -> None:
        from app.ingestion.scrapers.news_body import _fetch_body

        article = MagicMock()
        article.url = "https://example.com/article"
        article.source = "argaam_en"

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await _fetch_body(mock_client, article)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        from app.ingestion.scrapers.news_body import _fetch_body

        article = MagicMock()
        article.id = 42
        article.url = "https://example.com/article"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection error"))

        result = await _fetch_body(mock_client, article)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_body_on_success(self) -> None:
        from app.ingestion.scrapers.news_body import _fetch_body

        article = MagicMock()
        article.url = "https://example.com/article"
        article.source = "argaam_en"

        html = """<html><body>
            <article>
                <p>Industrial warehouse rents in Riyadh rose by 8% in Q4 2024 according
                to new data from MODON and real estate consultants tracking the market.</p>
                <p>Supply constraints in key districts pushed vacancy rates to record lows
                while demand from logistics operators remained strong throughout the year.</p>
            </article>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await _fetch_body(mock_client, article)
        assert result is not None
        assert len(result) > 50


class TestRunNewsBodyFetcher:
    @pytest.mark.asyncio
    async def test_skips_when_not_live_mode(self) -> None:
        from app.ingestion.scrapers.news_body import run_news_body_fetcher

        with patch("app.ingestion.scrapers.news_body.settings") as mock_settings:
            mock_settings.scraper_live_mode = False
            result = await run_news_body_fetcher()
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_articles(self) -> None:
        from app.ingestion.scrapers.news_body import run_news_body_fetcher

        mock_result = MagicMock()
        mock_result.scalars.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.ingestion.scrapers.news_body.settings") as mock_settings,
            patch(
                "app.ingestion.scrapers.news_body.AsyncSessionFactory", return_value=mock_session
            ),
        ):
            mock_settings.scraper_live_mode = True
            mock_settings.ksa_proxy_url = None
            result = await run_news_body_fetcher()
        assert result == 0
