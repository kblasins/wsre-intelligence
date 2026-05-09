"""Tests for the outbox reconciler's extractor dispatch table."""

from __future__ import annotations


class TestGetExtractor:
    """_get_extractor should return the right callable for each known source."""

    def test_tadawul_resolves(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        fn = _get_extractor("tadawul")
        assert fn is not None
        assert callable(fn)

    def test_aqar_resolves(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        fn = _get_extractor("aqar")
        assert fn is not None
        assert callable(fn)

    def test_news_sources_resolve(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        for source in ("news", "argaam_en", "argaam_ar", "saudi_gazette", "arab_news"):
            fn = _get_extractor(source)
            assert fn is not None, f"No extractor for {source}"
            assert callable(fn)

    def test_pdf_sources_resolve(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        for source in ("knight_frank", "cbre", "jll"):
            fn = _get_extractor(source)
            assert fn is not None, f"No extractor for {source}"
            assert callable(fn)

    def test_modon_resolves(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        fn = _get_extractor("modon")
        assert fn is not None
        assert callable(fn)

    def test_knight_frank_resolves(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        fn = _get_extractor("knight_frank")
        assert fn is not None
        assert callable(fn)

    def test_unknown_source_returns_none(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        assert _get_extractor("unknown_portal_xyz") is None

    def test_empty_string_returns_none(self) -> None:
        from app.ingestion.reconciler import _get_extractor

        assert _get_extractor("") is None
