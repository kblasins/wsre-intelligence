"""Tests for app.briefing.pdf_render — HTML generation and render dispatch."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.briefing.pdf_render import _build_pdf_html, render_brief_pdf


def _make_brief(text: str = "# Title\n\nContent.") -> MagicMock:
    brief = MagicMock()
    brief.brief_text = text
    brief.week_ending = datetime.date(2025, 6, 8)
    brief.cost_usd = 0.25
    brief.model_id = "claude-opus-4-6"
    brief.pdf_uri = None
    return brief


# ── _build_pdf_html ─────────────────────────────────────────────────────────────


class TestBuildPdfHtml:
    def test_doctype_present(self):
        html = _build_pdf_html(_make_brief())
        assert "<!DOCTYPE html>" in html

    def test_print_css_media_query(self):
        html = _build_pdf_html(_make_brief())
        assert "@media print" in html

    def test_contains_wordmark(self):
        html = _build_pdf_html(_make_brief())
        assert "White Star" in html

    def test_contains_tagline(self):
        html = _build_pdf_html(_make_brief())
        assert "Riyadh Industrial" in html

    def test_week_date_formatted(self):
        html = _build_pdf_pdf = _build_pdf_html(_make_brief())
        assert "8 June 2025" in html

    def test_cost_in_footer(self):
        html = _build_pdf_html(_make_brief())
        assert "$0.2500" in html

    def test_model_id_in_footer(self):
        html = _build_pdf_html(_make_brief())
        assert "claude-opus-4-6" in html

    def test_light_background_for_print(self):
        html = _build_pdf_html(_make_brief())
        assert "background: #fff" in html

    def test_body_content_present(self):
        html = _build_pdf_html(_make_brief("## Section\n\nSome data."))
        assert "Section" in html
        assert "Some data" in html


# ── render_brief_pdf ────────────────────────────────────────────────────────────


class TestRenderBriefPdf:
    @pytest.mark.asyncio
    async def test_returns_none_when_playwright_missing(self):
        brief = _make_brief()
        session = AsyncMock()

        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            # When import fails, render_brief_pdf should return None gracefully.
            # We simulate by patching the internal import.
            with patch("app.briefing.pdf_render.render_brief_pdf", wraps=None):
                pass  # just verifying the module doesn't crash on import

        # Direct test: patch the import inside the function
        import builtins

        real_import = builtins.__import__

        def _fail_playwright(name, *args, **kwargs):
            if "playwright" in name:
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fail_playwright):
            result = await render_brief_pdf(brief, session)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_playwright_error(self):
        """Playwright available but launch fails — should return None, not raise."""
        brief = _make_brief()
        session = AsyncMock()

        mock_pw_ctx = MagicMock()
        mock_pw_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("chromium not found"))
        mock_pw_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_async_playwright = MagicMock(return_value=mock_pw_ctx)

        import sys
        import types

        # Inject a fake playwright.async_api module so the local import succeeds
        fake_pw_module = types.ModuleType("playwright.async_api")
        fake_pw_module.async_playwright = mock_async_playwright  # type: ignore[attr-defined]
        fake_storage_module = types.ModuleType("app.core.storage")
        fake_storage_module.upload_raw = AsyncMock(return_value=("s3://x", {}))  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {
                "playwright": types.ModuleType("playwright"),
                "playwright.async_api": fake_pw_module,
            },
        ):
            result = await render_brief_pdf(brief, session)

        assert result is None

    @pytest.mark.asyncio
    async def test_successful_render_updates_brief_uri(self):
        """Full happy path with all Playwright internals mocked."""
        import sys
        import types

        brief = _make_brief()
        session = AsyncMock()

        # Mock the page
        mock_page = AsyncMock()
        mock_page.set_content = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=b"%PDF-fake-content")

        # Mock browser
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        # Mock chromium
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        # Mock playwright context manager
        mock_pw = MagicMock()
        mock_pw.chromium = mock_chromium
        mock_pw_ctx = MagicMock()
        mock_pw_ctx.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_async_playwright = MagicMock(return_value=mock_pw_ctx)

        mock_upload = AsyncMock(return_value=("s3://bucket/brief-20250608.pdf", {}))

        fake_pw_module = types.ModuleType("playwright.async_api")
        fake_pw_module.async_playwright = mock_async_playwright  # type: ignore[attr-defined]

        with (
            patch.dict(
                sys.modules,
                {
                    "playwright": types.ModuleType("playwright"),
                    "playwright.async_api": fake_pw_module,
                },
            ),
            patch("app.core.storage.upload_raw", mock_upload),
        ):
            result = await render_brief_pdf(brief, session)

        assert result == "s3://bucket/brief-20250608.pdf"
        assert brief.pdf_uri == "s3://bucket/brief-20250608.pdf"
        session.commit.assert_called_once()
        mock_page.pdf.assert_called_once()
