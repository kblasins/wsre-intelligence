"""Unit tests for the Tadawul scraper (no live HTTP calls).

Uses pytest-recording (VCR cassettes) to replay saved yfinance responses.
Cassette files live in tests/cassettes/ — generate them with:
    pytest --record-mode=once tests/test_tadawul.py
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.ingestion.scrapers.tadawul import REIT_TICKERS, _upsert_from_df


@pytest.mark.unit
async def test_industrial_reits_are_in_ticker_list() -> None:
    """The three priority industrial REITs must be present and correctly tagged."""
    tickers = {r["ticker"]: r for r in REIT_TICKERS}
    for ticker, _name in [
        ("4331.SR", "AlJazira Mawten REIT"),
        ("4339.SR", "Derayah REIT"),
        ("4340.SR", "Al Rajhi REIT"),
    ]:
        assert ticker in tickers, f"{ticker} missing from REIT_TICKERS"
        assert tickers[ticker]["industrial"] == "yes", f"{ticker} should be marked industrial=yes"


@pytest.mark.unit
async def test_upsert_from_df_handles_nan_gracefully(db_session) -> None:
    """NaN prices (market closed, no trades) should not insert rows or raise."""
    import numpy as np

    # Build a minimal MultiIndex DataFrame with one NaN ticker
    arrays = [["Close", "Close"], ["4331.SR", "4339.SR"]]
    columns = pd.MultiIndex.from_arrays(arrays)
    df = pd.DataFrame(
        [[np.nan, 12.50]],
        columns=columns,
        index=pd.date_range("2026-04-14", periods=1),
    )

    count = await _upsert_from_df(db_session, df, "s3://test/blob.json.gz", date(2026, 4, 14))
    # 4331 is NaN → skipped; 4339 is 12.50 → inserted
    assert count == 1
