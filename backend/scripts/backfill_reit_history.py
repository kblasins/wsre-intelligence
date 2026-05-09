"""REIT 2-year historical price backfill via yfinance.

One-time script — downloads 2 years of daily close prices for all 19 Tadawul
REITs and upserts into reit_snapshots. Run manually:

    python scripts/backfill_reit_history.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf
from sqlalchemy.dialects.postgresql import insert

from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging
from app.core.storage import upload_raw
from app.ingestion.scrapers.tadawul import REIT_TICKERS
from app.models.market import ReitSnapshot

import structlog

log = structlog.get_logger(__name__)


async def backfill() -> int:
    tickers = [r["ticker"] for r in REIT_TICKERS]
    log.info("reit_backfill_start", tickers=len(tickers), period="2y")

    raw_df = yf.download(
        tickers,
        period="2y",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if raw_df.empty:
        log.error("reit_backfill_no_data")
        return 0

    # Store raw blob
    raw_bytes = raw_df.to_json(date_format="iso").encode()
    ts = datetime.now(UTC)
    uri, _ = await upload_raw(
        raw_bytes, "tadawul_backfill", "json", content_type="application/json", ts=ts
    )

    total_upserted = 0
    close_df = raw_df.get("Close")
    if close_df is None:
        log.error("reit_backfill_no_close_column")
        return 0

    async with AsyncSessionFactory() as session:
        for date_idx, row in close_df.iterrows():
            snapshot_date = date_idx.date() if hasattr(date_idx, "date") else date_idx
            for reit in REIT_TICKERS:
                ticker = reit["ticker"]
                price = row.get(ticker)
                if price is None or (price != price):  # NaN check
                    continue
                price = float(price)

                stmt = (
                    insert(ReitSnapshot)
                    .values(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        price_sar=price,
                        raw_uri=uri,
                        extracted_at=ts,
                        model_id=None,
                        raw_json={
                            "ticker": ticker,
                            "name": reit["name"],
                            "industrial": reit["industrial"],
                            "price_sar": price,
                            "source": "yfinance_backfill",
                            "delay_minutes": 0,
                        },
                    )
                    .on_conflict_do_update(
                        constraint="uq_reit_ticker_date",
                        set_={
                            "price_sar": price,
                            "raw_uri": uri,
                            "extracted_at": ts,
                        },
                    )
                )
                await session.execute(stmt)
                total_upserted += 1

        await session.commit()

    log.info("reit_backfill_done", rows=total_upserted)
    return total_upserted


if __name__ == "__main__":
    configure_logging()
    result = asyncio.run(backfill())
    print(f"Backfilled {result} REIT price rows.")
