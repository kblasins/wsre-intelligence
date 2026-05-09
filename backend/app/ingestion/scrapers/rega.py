"""REGA / SREM transaction indicator scraper.

STATUS: PERMANENT STUB — srem.moj.gov.sa is Nafath-gated (Saudi national ID
authentication). Scraping it is out of scope under the project's pragmatic legal
posture (Anti-Cyber Crime Law Articles 3-5; Nafath terms prohibit automated access).

SANCTIONED REPLACEMENT PATH: REGA Open Data request submitted 18 Apr 2026 at
  https://rega.gov.sa/en/open-data/request-open-data/
Expected response: 30-90 days. When REGA responds, implement the data ingestion
based on the format they provide (likely CSV download or API key). Update this
file at that point — the scrape() method below can be replaced with a simple
file-parser or API client without changes to any other pipeline code.

Until REGA responds:
  - Transaction count in evaluate panels shows 0 with an explicit notice.
  - The weekly brief states the gap and lists the secondary sources in use.
  - Do not attempt to access srem.moj.gov.sa — no DevTools capture, no proxy,
    no Playwright session. The Open Data channel is the only sanctioned path.

PDPL note: Once REGA provides data, verify field-by-field that no personal
identifiers (buyer/seller names, national IDs) are included. Aggregates only.
If any personal identifier appears, treat as PDPL in-scope before sending to
Anthropic.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.ingestion.base import EXTRACTOR_VERSION, BaseScraper
from app.models.ingestion import RawIngestOutbox
from app.models.market import Transaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# ── TO BE FILLED AFTER DEVTOOLS CAPTURE ───────────────────────────────────────
# These constants are placeholders until the live XHR is captured.
PORTAL_BASE_URL = "https://srem.moj.gov.sa"
API_HOST = "https://prod-srem-business-api-srem.moj.gov.sa/api/v1"
# Example — replace with actual endpoint path from DevTools:
# API_TRANSACTIONS_PATH = "/transactions/indicators/filter"
API_TRANSACTIONS_PATH = "__NEEDS_DEVTOOLS_CAPTURE__"

# Playwright session state file — persists cookies across scraper runs
STATE_FILE = Path(settings.playwright_state_dir) / "rega_state.json"

# Known-good Arabic→English field map (from REGA public documentation)
FIELD_MAP: dict[str, str] = {
    "مبلغ الصفقة": "price_sar",
    "المساحة": "area_sqm",
    "الحي": "district",
    "المدينة": "city",
    "المنطقة": "region",
    "تاريخ الصفقة": "transaction_date",
    "نوع العقار": "property_type",
    "السعر للمتر": "price_per_sqm",
    "نوع الصفقة": "transaction_type",
    # Deed number (رقم الصك) and real estate ID (الهوية العقارية) are OMITTED —
    # they could identify individual properties and fall under PDPL if linked to persons.
}

# Property type normalization (Arabic → canonical enum value)
PROPERTY_TYPE_MAP: dict[str, str] = {
    "مستودع": "warehouse",
    "أرض صناعية": "industrial_land",
    "مصنع": "factory",
    "لوجستي": "logistics",
    "مكتب": "office",
    "تجاري": "retail",
    "سكني": "residential",
}

TRANSACTION_TYPE_MAP: dict[str, str] = {
    "بيع": "sale",
    "إيجار": "lease",
    "رهن": "mortgage",
}


async def run_rega_scraper() -> None:
    """Entry point for APScheduler — fetches REGA indicators for the past 7 days."""
    if API_TRANSACTIONS_PATH == "__NEEDS_DEVTOOLS_CAPTURE__":
        log.warning(
            "rega_scraper_stub",
            message=(
                "REGA scraper is a stub pending DevTools XHR capture. "
                "Open srem.moj.gov.sa in Chrome, capture the transaction XHR, "
                "and fill in API_TRANSACTIONS_PATH in this file."
            ),
        )
        return

    if not settings.scraper_live_mode:
        log.info("rega_scraper_skipped", reason="SCRAPER_LIVE_MODE=false")
        return

    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    scraper = RegaScraper()
    await scraper.run(start_date=start_date, end_date=end_date)


class RegaScraper(BaseScraper):
    SOURCE = "rega"

    async def run(self, start_date: date, end_date: date) -> None:
        """Fetch REGA indicators for a date range, store raw blob, upsert rows."""

        log.info("rega_scraper_start", start=str(start_date), end=str(end_date))

        # ── Step 1: Playwright warm-up to get Akamai cookies ─────────────────
        # (Only needed if the session state file has expired or doesn't exist)
        if not STATE_FILE.exists() or _state_is_stale():
            await self._warm_up_playwright()

        # ── Step 2: curl_cffi for the actual API call ─────────────────────────
        # curl_cffi with impersonate="chrome124" presents the correct JA3/JA4
        # TLS fingerprint that Akamai expects. Raw Python requests get flagged.
        from curl_cffi import requests as cffi_requests

        cookies = _load_state_cookies()
        params = _build_query_params(start_date, end_date)

        session = cffi_requests.Session(impersonate="chrome124")
        resp = session.get(
            f"{API_HOST}{API_TRANSACTIONS_PATH}",
            params=params,
            cookies=cookies,
            headers={
                "Accept": "application/json",
                "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8",
                "Referer": PORTAL_BASE_URL,
            },
        )
        resp.raise_for_status()

        raw_bytes = resp.content
        uri, sha1 = await self.save_raw(raw_bytes, "json", content_type="application/json")

        data = resp.json()
        rows = _parse_response(data)

        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as db_session:
            outbox_row = RawIngestOutbox(
                source=self.SOURCE,
                raw_uri=uri,
                content_sha1=sha1,
                content_type="application/json",
                structured=0,
                scraper_meta={"start_date": str(start_date), "end_date": str(end_date)},
            )
            db_session.add(outbox_row)
            await db_session.flush()

            count = await _upsert_rows(db_session, rows, uri)

            outbox_row.structured = 1
            outbox_row.structured_at = datetime.now(UTC)
            await db_session.commit()

        log.info("rega_scraper_done", rows_upserted=count, uri=uri)

    async def _warm_up_playwright(self) -> None:
        """Load the REGA portal with full browser to establish Akamai session."""
        import random

        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        # Rotate from a small pool of plausible user agents
        UA_POOL = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": settings.ksa_proxy_url} if settings.ksa_proxy_url else None,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--lang=ar-SA,ar,en-US,en",
                ],
            )
            ctx = await browser.new_context(
                user_agent=random.choice(UA_POOL),
                locale="ar-SA",
                timezone_id="Asia/Riyadh",
                viewport={"width": 1366, "height": 768},
                storage_state=str(STATE_FILE) if STATE_FILE.exists() else None,
            )
            await Stealth().apply_stealth_async(ctx)

            page = await ctx.new_page()
            await page.goto(PORTAL_BASE_URL, wait_until="networkidle", timeout=45_000)
            # Wait for JS to execute and Akamai to issue its cookies
            await page.wait_for_timeout(random.randint(1500, 3000))

            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(STATE_FILE))
            await browser.close()

        log.info("rega_playwright_warmup_done", state_file=str(STATE_FILE))


def _state_is_stale() -> bool:
    """State file older than 6 hours needs refresh (Akamai cookie TTL)."""
    if not STATE_FILE.exists():
        return True
    age = datetime.now(UTC).timestamp() - STATE_FILE.stat().st_mtime
    return age > 6 * 3600


def _load_state_cookies() -> dict[str, str]:
    """Load cookies from the Playwright storage state file."""

    state = json.loads(STATE_FILE.read_text())
    return {c["name"]: c["value"] for c in state.get("cookies", [])}


def _build_query_params(start_date: date, end_date: date) -> dict[str, str]:
    """Build query parameters for the REGA API call.

    PLACEHOLDER — replace with actual parameter names after DevTools capture.
    """
    return {
        "regionCode": "01",  # Riyadh region — verify code from DevTools
        "cityCode": "0101",  # Riyadh city — verify
        "propertyType": "3",  # Industrial/warehouse — verify code
        "dateFrom": start_date.isoformat(),
        "dateTo": end_date.isoformat(),
        "pageSize": "200",
        "pageNumber": "1",
    }


def _parse_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the REGA API JSON response into normalized transaction dicts.

    PLACEHOLDER — replace with actual field parsing after DevTools capture.
    The structure below is a best-guess from the public API documentation;
    the real shape will differ.
    """
    results = data.get("data", data.get("transactions", data.get("items", [])))
    parsed = []
    for row in results:
        try:
            parsed.append(
                {
                    "transaction_date": _parse_date(
                        row.get("تاريخ الصفقة") or row.get("transactionDate")
                    ),
                    "district": row.get("الحي") or row.get("district") or "Unknown",
                    "city": row.get("المدينة") or row.get("city") or "Riyadh",
                    "region": row.get("المنطقة") or row.get("region") or "Riyadh Region",
                    "property_type": _map_property_type(
                        row.get("نوع العقار") or row.get("propertyType", "")
                    ),
                    "transaction_type": _map_transaction_type(
                        row.get("نوع الصفقة") or row.get("transactionType", "بيع")
                    ),
                    "area_sqm": _parse_float(row.get("المساحة") or row.get("area")),
                    "price_sar": _parse_float(row.get("مبلغ الصفقة") or row.get("amount")),
                    "source_id": str(row.get("id") or row.get("transactionId") or ""),
                    "raw_json": row,
                    "source_priority": 1,
                    "extractor_version": EXTRACTOR_VERSION,
                }
            )
        except Exception as exc:
            log.warning("rega_parse_row_failed", error=str(exc), row=str(row)[:200])
    return parsed


async def _upsert_rows(session: AsyncSession, rows: list[dict[str, Any]], raw_uri: str) -> int:
    count = 0
    now = datetime.now(UTC)
    for row in rows:
        if not row.get("price_sar") or row["price_sar"] <= 0:
            continue
        row_data = {**row, "raw_uri": raw_uri, "extracted_at": now}
        stmt = (
            insert(Transaction)
            .values(**row_data)
            .on_conflict_do_update(
                constraint="uq_transactions_source_id",
                set_={"price_sar": row["price_sar"], "raw_uri": raw_uri, "extracted_at": now},
            )
        )
        await session.execute(stmt)
        count += 1
    return count


async def extract_from_blob(
    session: AsyncSession,
    raw_bytes: bytes,
    outbox_row: RawIngestOutbox,
) -> None:
    """Re-extraction entry point for the outbox reconciler."""

    data = json.loads(raw_bytes.decode())
    rows = _parse_response(data)
    await _upsert_rows(session, rows, outbox_row.raw_uri)


# ── Parsing helpers ────────────────────────────────────────────────────────────


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _map_property_type(value: str) -> str:
    normalized = value.strip()
    return PROPERTY_TYPE_MAP.get(normalized, "other")


def _map_transaction_type(value: str) -> str:
    normalized = value.strip()
    return TRANSACTION_TYPE_MAP.get(normalized, "sale")


if __name__ == "__main__":
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    asyncio.run(run_rega_scraper())
