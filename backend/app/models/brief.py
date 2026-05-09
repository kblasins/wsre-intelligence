"""Weekly intelligence brief model.

One row per brief generated. The brief_text is the full Opus-authored markdown.
brief_json contains parsed sections for structured access by the API.
pdf_uri points to the rendered PDF in blob storage (null until PDF job runs).
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class WeeklyBrief(Base):
    __tablename__ = "weekly_briefs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # The Sunday the brief covers (week_ending = generation date for Sunday runs)
    week_ending: Mapped[date] = mapped_column(Date, nullable=False, unique=True)

    # Full Opus-authored markdown
    brief_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Parsed sections for API/frontend access
    brief_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Data lineage
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_sha: Mapped[str] = mapped_column(String(12), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.0)

    # PDF (null until Playwright render job completes)
    pdf_uri: Mapped[str | None] = mapped_column(Text, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
