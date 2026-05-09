"""Unit tests for the news extractor (no Anthropic API calls).

Tests cover:
- _compute_cost: pure function, token pricing math
- _prompt_sha: deterministic SHA computation
- run_news_extractor skips when budget is paused
- DB wiring: articles with null relevance_score are queryable
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.ingestion.extractors.news import (
    HAIKU_MODEL,
    PRICING,
    SONNET_MODEL,
    _compute_cost,
    _prompt_sha,
)
from app.models.market import NewsArticle

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── Pure function tests ────────────────────────────────────────────────────────


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


@pytest.mark.unit
def test_compute_cost_haiku_no_cache() -> None:
    usage = _FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = _compute_cost(usage, HAIKU_MODEL)
    expected = PRICING[HAIKU_MODEL]["input"] + PRICING[HAIKU_MODEL]["output"]
    assert abs(cost - expected) < 1e-9


@pytest.mark.unit
def test_compute_cost_sonnet_no_cache() -> None:
    usage = _FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = _compute_cost(usage, SONNET_MODEL)
    expected = PRICING[SONNET_MODEL]["input"] + PRICING[SONNET_MODEL]["output"]
    assert abs(cost - expected) < 1e-9


@pytest.mark.unit
def test_compute_cost_zero_tokens() -> None:
    usage = _FakeUsage(input_tokens=0, output_tokens=0)
    assert _compute_cost(usage, HAIKU_MODEL) == 0.0


@pytest.mark.unit
def test_compute_cost_with_cache_read() -> None:
    class UsageWithCache(_FakeUsage):
        cache_read_input_tokens = 1_000_000

    usage = UsageWithCache(input_tokens=0, output_tokens=0)
    cost = _compute_cost(usage, HAIKU_MODEL)
    assert abs(cost - PRICING[HAIKU_MODEL]["cache_read"]) < 1e-9


@pytest.mark.unit
def test_prompt_sha_deterministic() -> None:
    sha1 = _prompt_sha("system text", "user template")
    sha2 = _prompt_sha("system text", "user template")
    assert sha1 == sha2
    assert len(sha1) == 12


@pytest.mark.unit
def test_prompt_sha_differs_on_change() -> None:
    sha1 = _prompt_sha("system A", "user template")
    sha2 = _prompt_sha("system B", "user template")
    assert sha1 != sha2


# ── Budget gate ────────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_extractor_skips_when_budget_paused() -> None:
    """run_news_extractor should return immediately when budget is paused."""
    from app.ingestion.extractors.news import run_news_extractor

    with (
        patch("app.ingestion.extractors.news.is_batch_paused", return_value=True),
        patch("app.ingestion.extractors.news.AsyncSessionFactory") as mock_factory,
    ):
        # Should not raise and should not open any DB session
        await run_news_extractor()
        mock_factory.assert_not_called()


# ── DB integration ─────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_article_needs_triage_query(db_session: AsyncSession) -> None:
    """Articles with null relevance_score show up in the triage query."""
    from sqlalchemy import select

    article = NewsArticle(
        source="argaam_en",
        external_id="test-triage-001",
        title_en="MODON announces new industrial city in Riyadh",
        url="https://example.com/article/001",
        published_at=datetime.now(UTC),
        raw_uri="local://test",
        extracted_at=datetime.now(UTC),
        relevance_score=None,
    )
    db_session.add(article)
    await db_session.flush()

    result = await db_session.execute(
        select(NewsArticle).where(NewsArticle.relevance_score.is_(None))
    )
    unscored = list(result.scalars())
    assert any(a.external_id == "test-triage-001" for a in unscored)


@pytest.mark.unit
async def test_scored_article_not_in_triage_query(db_session: AsyncSession) -> None:
    """Articles with a score set do NOT appear in the triage queue."""
    from sqlalchemy import select

    article = NewsArticle(
        source="argaam_en",
        external_id="test-triage-002",
        title_en="Already scored article",
        url="https://example.com/article/002",
        published_at=datetime.now(UTC),
        raw_uri="local://test",
        extracted_at=datetime.now(UTC),
        relevance_score=0.8,
    )
    db_session.add(article)
    await db_session.flush()

    result = await db_session.execute(
        select(NewsArticle).where(NewsArticle.relevance_score.is_(None))
    )
    unscored = list(result.scalars())
    assert not any(a.external_id == "test-triage-002" for a in unscored)
