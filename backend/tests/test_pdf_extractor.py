"""Tests for the PDF extraction pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPdfToMarkdown:
    """_pdf_to_markdown should convert PDF bytes to a string."""

    def test_returns_string_from_valid_pdf(self) -> None:
        """Smoke test: given a minimal valid PDF, returns a string."""
        from app.pdf.extractor import _pdf_to_markdown

        # Minimal PDF header to pass the check — pymupdf4llm will still parse it
        fake_pdf = b"%PDF-1.4 1 0 obj<</Type/Catalog>>endobj"
        with patch(
            "pymupdf4llm.to_markdown", return_value="# Report\n\nRent SAR 120/sqm"
        ) as mock_md:
            result = _pdf_to_markdown(fake_pdf)
        mock_md.assert_called_once()
        assert isinstance(result, str)
        assert result == "# Report\n\nRent SAR 120/sqm"

    def test_propagates_exception_on_corrupt_pdf(self) -> None:
        from app.pdf.extractor import _pdf_to_markdown

        with (
            patch("pymupdf4llm.to_markdown", side_effect=RuntimeError("corrupt")),
            pytest.raises(RuntimeError, match="corrupt"),
        ):
            _pdf_to_markdown(b"not a pdf")


class TestExtractFacts:
    """_extract_facts should call the Anthropic API and parse JSON."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_valid_json(self) -> None:
        from app.pdf.extractor import _extract_facts

        payload = {
            "report_title": "KSA Industrial 2024",
            "rent_indices": [{"district": "Riyadh", "rent_sar_sqm_annual": 120.0}],
            "confidence": 4,
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(payload))]
        mock_response.usage = MagicMock(
            input_tokens=500,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        facts, _usage = await _extract_facts(mock_client, "# Report content", "kf-ksa-2024")

        assert facts["report_title"] == "KSA Industrial 2024"
        assert facts["confidence"] == 4
        assert len(facts["rent_indices"]) == 1

    @pytest.mark.asyncio
    async def test_falls_back_on_invalid_json(self) -> None:
        from app.pdf.extractor import _extract_facts

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON at all")]
        mock_response.usage = MagicMock(
            input_tokens=100,
            output_tokens=20,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        facts, _usage = await _extract_facts(mock_client, "garbage content", "slug")

        assert "_raw_response" in facts
        assert facts["confidence"] == 1

    @pytest.mark.asyncio
    async def test_content_is_truncated_to_max_chars(self) -> None:
        """Ensure very long PDFs are truncated before hitting the API."""
        from app.pdf.extractor import MAX_PDF_CHARS, _extract_facts

        long_content = "x" * (MAX_PDF_CHARS + 50_000)

        captured: list[str] = []

        async def _fake_create(**kwargs):  # type: ignore[no-untyped-def]
            msg = kwargs["messages"][0]["content"]
            captured.append(msg)
            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text='{"confidence": 3}')]
            mock_resp.usage = MagicMock(
                input_tokens=100,
                output_tokens=10,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            )
            return mock_resp

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = _fake_create

        await _extract_facts(mock_client, long_content, "slug")

        assert len(captured) == 1
        # The user message must not contain more chars than MAX_PDF_CHARS
        assert long_content[:MAX_PDF_CHARS] in captured[0]
        assert "x" * (MAX_PDF_CHARS + 1) not in captured[0]


class TestPromptSha:
    def test_is_deterministic(self) -> None:
        from app.pdf.extractor import _prompt_sha

        assert _prompt_sha() == _prompt_sha()

    def test_is_12_hex_chars(self) -> None:
        from app.pdf.extractor import _prompt_sha

        sha = _prompt_sha()
        assert len(sha) == 12
        assert all(c in "0123456789abcdef" for c in sha)
