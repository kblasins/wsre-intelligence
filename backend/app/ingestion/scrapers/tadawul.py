"""Tadawul REIT price scraper — yfinance (15-min delayed, zero cost, low ToS risk).

Coverage: all 19 listed REITs, with priority tracking for the three
industrial-exposed names: 4331 (AlJazira Mawten), 4339 (Derayah), 4340 (Al Rajhi).

NAV and distribution history are NOT available from yfinance. Those come from
PDF parsing (Tadawul issuer announcements + fund manager IR sites) in Phase 2.
Occupancy is flagged as a known gap in the product.

The raw_first pattern here stores the JSON response from yfinance before
any DB upsert. This lets us replay extraction if the ReitSnapshot schema changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import structlog
import yfinance as yf
from sqlalchemy.dialects.postgresql import insert

from app.core.database import AsyncSessionFactory
from app.core.storage import upload_raw
from app.models.ingestion import RawIngestOutbox
from app.models.market import ReitSnapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# All Tadawul-listed REITs as of April 2026.
# Priority industrial names first — used in the exit cap-rate model for MODON R1.
REIT_TICKERS: list[dict[str, str]] = [
    {"ticker": "4331.SR", "name": "AlJazira Mawten REIT", "industrial": "yes"},
    {"ticker": "4339.SR", "name": "Derayah REIT", "industrial": "yes"},
    {"ticker": "4340.SR", "name": "Al Rajhi REIT", "industrial": "yes"},
    {"ticker": "4330.SR", "name": "Riyad REIT", "industrial": "verify"},
    {"ticker": "4332.SR", "name": "Jadwa REIT Al Haramain", "industrial": "no"},
    {"ticker": "4333.SR", "name": "Taleem REIT", "industrial": "no"},
    {"ticker": "4334.SR", "name": "Al Maather REIT", "industrial": "verify"},
    {"ticker": "4335.SR", "name": "Musharaka REIT", "industrial": "verify"},
    {"ticker": "4336.SR", "name": "Mulkia Gulf RE REIT", "industrial": "verify"},
    {"ticker": "4337.SR", "name": "SICO Saudi REIT", "industrial": "verify"},
    {"ticker": "4338.SR", "name": "Alahli REIT 1", "industrial": "verify"},
    {"ticker": "4342.SR", "name": "Jadwa REIT Saudi", "industrial": "verify"},
    {"ticker": "4344.SR", "name": "SEDCO Capital REIT", "industrial": "verify"},
    {"ticker": "4345.SR", "name": "Alinma Retail REIT", "industrial": "no"},
    {"ticker": "4346.SR", "name": "MEFIC REIT", "industrial": "verify"},
    {"ticker": "4347.SR", "name": "Bonyan REIT", "industrial": "verify"},
    {"ticker": "4348.SR", "name": "AlKhabeer REIT", "industrial": "verify"},
    {"ticker": "4349.SR", "name": "Alinma Hospitality REIT", "industrial": "no"},
    {"ticker": "4350.SR", "name": "Alistithmar REIT", "industrial": "verify"},
]


async def run_tadawul_scraper() -> None:
    """Entry point for APScheduler. Fetches all REIT prices and upserts.

    Called by the scheduler via BREAKERS["tadawul"].call_async(run_tadawul_scraper).
    Not decorated directly — pybreaker's decorator wraps async functions in a
    sync wrapper which breaks asyncio.
    """
    today = date.today()
    log.info("tadawul_scraper_start", date=str(today), ticker_count=len(REIT_TICKERS))

    tickers = [r["ticker"] for r in REIT_TICKERS]
    # yfinance download: batch all tickers in one API call
    # period="1d" returns today's OHLCV; auto_adjust=True adjusts for splits/dividends
    raw_df = yf.download(
        tickers,
        period="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    # Serialize the full DataFrame to JSON for raw preservation
    raw_json = raw_df.to_json(date_format="iso")
    raw_bytes = raw_json.encode()
    ts = datetime.now(UTC)
    uri, sha1 = await upload_raw(
        raw_bytes, "tadawul", "json", content_type="application/json", ts=ts
    )

    async with AsyncSessionFactory() as session:
        # Record outbox row — marks this blob as pending structured extraction
        outbox_row = RawIngestOutbox(
            source="tadawul",
            raw_uri=uri,
            content_sha1=sha1,
            content_type="application/json",
            structured=0,
            scraper_meta={"date": str(today), "tickers": tickers},
        )
        session.add(outbox_row)
        await session.flush()

        rows_upserted = await _upsert_from_df(session, raw_df, uri, today)

        # Mark outbox as structured (both happen in the same transaction)
        outbox_row.structured = 1
        outbox_row.structured_at = datetime.now(UTC)
        await session.commit()

    log.info("tadawul_scraper_done", rows_upserted=rows_upserted, uri=uri)


async def _upsert_from_df(
    session: AsyncSession, raw_df: Any, raw_uri: str, snapshot_date: date
) -> int:
    """Parse yfinance DataFrame and upsert ReitSnapshot rows.

    yfinance returns a MultiIndex DataFrame when multiple tickers are requested:
    columns are (OHLCV_field, ticker). We pivot to get one row per ticker.
    """
    count = 0
    for reit in REIT_TICKERS:
        ticker = reit["ticker"]
        try:
            # MultiIndex access: ("Close", "4331.SR")
            close_series = raw_df.get(("Close", ticker))
            if close_series is None or close_series.empty:
                log.warning("tadawul_no_data", ticker=ticker)
                continue

            price = float(close_series.iloc[-1])
            if price != price:  # NaN check
                log.warning("tadawul_nan_price", ticker=ticker)
                continue

            row_data = {
                "ticker": ticker,
                "snapshot_date": snapshot_date,
                "price_sar": price,
                "raw_uri": raw_uri,
                "extracted_at": datetime.now(UTC),
                "model_id": None,  # no LLM involved in price fetching
                "raw_json": {
                    "ticker": ticker,
                    "name": reit["name"],
                    "industrial": reit["industrial"],
                    "price_sar": price,
                    "source": "yfinance",
                    "delay_minutes": 15,
                },
            }

            stmt = (
                insert(ReitSnapshot)
                .values(**row_data)
                .on_conflict_do_update(
                    constraint="uq_reit_ticker_date",
                    set_={
                        "price_sar": price,
                        "raw_uri": raw_uri,
                        "extracted_at": datetime.now(UTC),
                    },
                )
            )
            await session.execute(stmt)
            count += 1

        except Exception as exc:
            log.warning("tadawul_ticker_failed", ticker=ticker, error=str(exc))

    return count


async def extract_from_blob(
    session: AsyncSession,
    raw_bytes: bytes,
    outbox_row: RawIngestOutbox,
) -> None:
    """Re-extraction entry point called by the outbox reconciler.

    Parses a previously stored yfinance JSON blob and upserts ReitSnapshot rows.
    The date is recovered from the scraper_meta stored in the outbox row.
    """
    import pandas as pd

    snapshot_date_str = outbox_row.scraper_meta.get("date")
    if not snapshot_date_str:
        raise ValueError("outbox row missing 'date' in scraper_meta")

    snapshot_date = date.fromisoformat(snapshot_date_str)
    raw_df = pd.read_json(raw_bytes.decode())
    await _upsert_from_df(session, raw_df, outbox_row.raw_uri, snapshot_date)


if __name__ == "__main__":
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    asyncio.run(run_tadawul_scraper())
