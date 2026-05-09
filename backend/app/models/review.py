"""Human-in-the-loop review queue.

Any Claude extraction with confidence ≤ 3 (on a 1-5 self-rated scale) lands
here. The admin UI surfaces these for analyst review before the data enters the
briefing pipeline.

The golden set of ~50 PDFs + ~100 articles also uses this table — golden rows
have is_golden=True and carry the hand-labeled expected_output for regression
comparison.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import BigInteger, Boolean, DateTime, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_table: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # "transactions", "news_articles", etc.
    source_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_sha: Mapped[str | None] = mapped_column(String(12), nullable=True)

    confidence: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Claude self-rating 1-5; this row has ≤3"
    )
    # The raw LLM output that was below confidence threshold
    llm_output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Fields Claude flagged as uncertain
    uncertain_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Review outcome
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # "approved", "corrected", "rejected"
    corrected_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Golden set management
    is_golden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_output: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Hand-labeled ground truth for regression tests"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
