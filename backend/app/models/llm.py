"""LLM call accounting table.

Every Claude API call writes a row here with tokens, cost, cache status,
and the prompt SHA. This is how you find the expensive prompt that nobody
noticed — and how you verify the daily budget gate is working.

The cron job in app/core/budget.py reads this table and pauses batch
submissions when the daily cap is hit.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)  # "claude-sonnet-4-6"
    prompt_sha: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # SHA-256 of prompt template
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "triage", "extraction", "translation", "synthesis", "ad_hoc"

    # Token counts from the API response usage block
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Cost in USD, computed at call time from current pricing table
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.0)

    # Whether this was a batch API call (50% discount, 24h latency)
    is_batch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    batch_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Reference to the outbox row this call served, if applicable
    outbox_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Soft FK to news_articles.id — which article did this call enrich?
    article_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Success / failure
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
