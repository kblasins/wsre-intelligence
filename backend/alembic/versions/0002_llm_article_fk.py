"""Add article_id to llm_calls and polling indexes on news_articles.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17

article_id: soft FK from llm_calls to news_articles — lets you answer
"what did triage + extraction of article #N cost?" without a join.

Partial indexes on news_articles make the extractor's polling queries
(WHERE relevance_score IS NULL / WHERE structured_facts = '{}') fast
even when the table grows to millions of rows.
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS article_id BIGINT")

    # Index to find articles that need Haiku triage
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_article_needs_triage
            ON news_articles (created_at ASC)
            WHERE relevance_score IS NULL
        """
    )

    # Index to find articles that need Sonnet extraction
    # structured_facts = '{}' matches the default empty JSONB object
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_article_needs_extraction
            ON news_articles (relevance_score DESC, created_at ASC)
            WHERE relevance_score >= 0.5 AND structured_facts = '{}'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_article_needs_extraction")
    op.execute("DROP INDEX IF EXISTS ix_article_needs_triage")
    op.execute("ALTER TABLE llm_calls DROP COLUMN IF EXISTS article_id")
