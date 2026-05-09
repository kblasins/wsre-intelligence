"""Tests for app.briefing.email — markdown conversion and email dispatch."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.briefing.email import (
    _build_html,
    _build_plain,
    _inline_md,
    _md_to_html,
    send_brief_email,
)

# ── _inline_md ──────────────────────────────────────────────────────────────────


class TestInlineMd:
    def test_bold(self):
        assert "<strong>text</strong>" in _inline_md("**text**")

    def test_italic(self):
        assert "<em>word</em>" in _inline_md("*word*")

    def test_code(self):
        assert "<code>cmd</code>" in _inline_md("`cmd`")

    def test_score_badge(self):
        result = _inline_md("[0.87]")
        assert "class='score'" in result
        assert "0.87" in result

    def test_plain_text_unchanged(self):
        assert _inline_md("hello world") == "hello world"


# ── _md_to_html ─────────────────────────────────────────────────────────────────


class TestMdToHtml:
    def test_h1(self):
        html = _md_to_html("# Title")
        assert "<h1>Title</h1>" in html

    def test_h2(self):
        html = _md_to_html("## Section")
        assert "<h2>Section</h2>" in html

    def test_h3(self):
        html = _md_to_html("### Sub")
        assert "<h3>Sub</h3>" in html

    def test_bullet_list(self):
        html = _md_to_html("- item one\n- item two")
        assert "<ul>" in html
        assert "<li>item one</li>" in html
        assert "<li>item two</li>" in html
        assert "</ul>" in html

    def test_horizontal_rule(self):
        html = _md_to_html("---")
        assert "<hr>" in html

    def test_paragraph(self):
        html = _md_to_html("Some text here")
        assert "<p>Some text here</p>" in html

    def test_empty_line_becomes_br(self):
        html = _md_to_html("\n")
        assert "<br>" in html

    def test_full_brief_snippet(self):
        md = "### 1. Executive Summary\n\nMarket is **bullish** — vacancy at `3.2%`."
        html = _md_to_html(md)
        assert "<h3>" in html
        assert "<strong>bullish</strong>" in html
        assert "<code>3.2%</code>" in html


# ── _build_plain ────────────────────────────────────────────────────────────────


class TestBuildPlain:
    def _make_brief(self, text: str = "Hello brief."):
        brief = MagicMock()
        brief.brief_text = text
        brief.week_ending = datetime.date(2025, 6, 8)
        brief.cost_usd = 0.123
        brief.model_id = "claude-opus-4-6"
        return brief

    def test_contains_weekmark(self):
        plain = _build_plain(self._make_brief())
        assert "8 June 2025" in plain

    def test_contains_brief_text(self):
        plain = _build_plain(self._make_brief("my content"))
        assert "my content" in plain

    def test_contains_white_star(self):
        plain = _build_plain(self._make_brief())
        assert "WHITE STAR" in plain


# ── _build_html ─────────────────────────────────────────────────────────────────


class TestBuildHtml:
    def _make_brief(self):
        brief = MagicMock()
        brief.brief_text = "# Title\n\nBody text."
        brief.week_ending = datetime.date(2025, 6, 8)
        brief.cost_usd = 0.456
        brief.model_id = "claude-opus-4-6"
        return brief

    def test_is_valid_html(self):
        html = _build_html(self._make_brief())
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_contains_wordmark(self):
        html = _build_html(self._make_brief())
        assert "White Star" in html

    def test_contains_week_date(self):
        html = _build_html(self._make_brief())
        assert "8 June 2025" in html

    def test_contains_model_id(self):
        html = _build_html(self._make_brief())
        assert "claude-opus-4-6" in html

    def test_contains_cost(self):
        html = _build_html(self._make_brief())
        assert "$0.4560" in html

    def test_dark_background(self):
        html = _build_html(self._make_brief())
        assert "#0e0e0e" in html


# ── send_brief_email ────────────────────────────────────────────────────────────


class TestSendBriefEmail:
    def _make_brief(self):
        brief = MagicMock()
        brief.brief_text = "Brief text."
        brief.week_ending = datetime.date(2025, 6, 8)
        brief.cost_usd = 0.1
        brief.model_id = "claude-opus-4-6"
        return brief

    @pytest.mark.asyncio
    async def test_returns_false_when_no_recipients(self):
        brief = self._make_brief()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.get_brief_recipients.return_value = []
            mock_settings.smtp_host = "smtp.example.com"
            result = await send_brief_email(brief)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_smtp_host(self):
        brief = self._make_brief()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.get_brief_recipients.return_value = ["a@b.com"]
            mock_settings.smtp_host = None
            result = await send_brief_email(brief)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        brief = self._make_brief()
        with (
            patch("app.core.config.settings") as mock_settings,
            patch("app.briefing.email.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            mock_settings.get_brief_recipients.return_value = ["recipient@example.com"]
            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user"
            mock_settings.smtp_password = "pass"
            mock_settings.smtp_from = "noreply@example.com"
            mock_thread.return_value = None

            result = await send_brief_email(brief)

        assert result is True
        mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_smtp_error(self):
        brief = self._make_brief()
        with (
            patch("app.core.config.settings") as mock_settings,
            patch("app.briefing.email.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            mock_settings.get_brief_recipients.return_value = ["recipient@example.com"]
            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = ""
            mock_settings.smtp_password = ""
            mock_settings.smtp_from = "noreply@example.com"
            mock_thread.side_effect = OSError("Connection refused")

            result = await send_brief_email(brief)

        assert result is False
