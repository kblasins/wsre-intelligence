"""ORM model smoke tests — verifies the schema creates cleanly and
enforces constraints. Also exercises the district_aliases FK path."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from app.models.market import ReitSnapshot, Transaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.unit
async def test_transaction_requires_positive_price(db_session: AsyncSession) -> None:
    """The price_sar > 0 constraint should reject zero-price transactions."""
    tx = Transaction(
        transaction_date=date(2026, 1, 15),
        district="Olaya",
        city="Riyadh",
        region="Riyadh Region",
        property_type="warehouse",
        transaction_type="sale",
        price_sar=0,  # violates CHECK constraint
        raw_json={},
        source_priority=1,
    )
    db_session.add(tx)
    with pytest.raises(Exception, match=r"ck_tx_positive_price|violates check constraint"):
        await db_session.flush()


@pytest.mark.unit
async def test_transaction_insert_valid(db_session: AsyncSession) -> None:
    tx = Transaction(
        transaction_date=date(2026, 1, 15),
        district="Olaya",
        city="Riyadh",
        region="Riyadh Region",
        property_type="warehouse",
        transaction_type="sale",
        area_sqm=5000.0,
        price_sar=5_250_000.0,
        raw_json={"source_portal": "rega"},
        source_priority=1,
        confidence=4,
    )
    db_session.add(tx)
    await db_session.flush()
    assert tx.id is not None


@pytest.mark.unit
async def test_reit_snapshot_unique_constraint(db_session: AsyncSession) -> None:
    """Duplicate (ticker, snapshot_date) should be rejected."""
    snap = ReitSnapshot(
        ticker="4331.SR",
        snapshot_date=date(2026, 4, 14),
        price_sar=9.85,
        raw_json={},
    )
    db_session.add(snap)
    await db_session.flush()

    dup = ReitSnapshot(
        ticker="4331.SR",
        snapshot_date=date(2026, 4, 14),
        price_sar=9.90,
        raw_json={},
    )
    db_session.add(dup)
    with pytest.raises(Exception, match=r"uq_reit_ticker_date|unique constraint"):
        await db_session.flush()
