"""Etimad Developer API scraper — Saudi government industrial tenders.

Etimad (developer.etimad.sa) is the official Saudi government e-procurement
platform. This scraper targets warehouse, industrial land, and MODON-related
construction tenders in Riyadh.

Auth: OAuth2 client credentials (ETIMAD_CLIENT_ID / ETIMAD_CLIENT_SECRET).
Rate limit: Etimad Developer API is documented at ≤60 req/min.

Design:
  1. Obtain bearer token via /identity/connect/token
  2. Page through /tender/api/tenders with keyword filters
  3. Save each response page as a JSON blob (raw-first)
  4. extract_from_blob() upserts Tender rows from the stored blob

Skip if credentials are not configured (graceful no-op in dev).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from app.core.config import settings
from app.ingestion.base import BaseScraper

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ingestion import RawIngestOutbox

log = structlog.get_logger(__name__)

# Etimad API base
_API_BASE = "https://tenders.etimad.sa/Tender/api"
_AUTH_URL = "https://tenders.etimad.sa/identity/connect/token"

# Search terms that catch industrial / warehouse tenders
_SEARCH_KEYWORDS = [
    "مستودع",  # warehouse
    "مخزن",  # storage
    "مصنع",  # factory
    "أرض صناعية",  # industrial land
    "مدينة صناعية",  # industrial city
    "لوجستي",  # logistics
    "MODON",
]

_PAGE_SIZE = 25


class EtimadScraper(BaseScraper):
    SOURCE = "etimad"

    async def _get_token(self) -> str:
        """OAuth2 client credentials token."""
        import httpx

        data = {
            "grant_type": "client_credentials",
            "client_id": settings.etimad_client_id,
            "client_secret": settings.etimad_client_secret,
            "scope": "TenderServiceScope",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(_AUTH_URL, data=data)
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def scrape(self, session: AsyncSession) -> int:
        """Fetch tenders and save raw blobs. Returns count of new blobs."""
        if not settings.etimad_client_id or not settings.etimad_client_secret:
            log.info("etimad_skip", reason="credentials_not_configured")
            return 0

        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        total_saved = 0

        for keyword in _SEARCH_KEYWORDS:
            page = 1
            while True:
                params: dict[str, Any] = {
                    "keyword": keyword,
                    "pageNumber": page,
                    "pageSize": _PAGE_SIZE,
                    "tendersStatusSelectedValue": "2",  # published / open
                }

                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.get(
                            f"{_API_BASE}/tenders",
                            headers=headers,
                            params=params,
                        )
                        resp.raise_for_status()
                        payload = resp.json()
                except Exception:
                    log.exception("etimad_page_failed", keyword=keyword, page=page)
                    break

                items = payload.get("result", payload.get("data", []))
                if not items:
                    break

                # Save raw blob
                raw = json.dumps(
                    {
                        "keyword": keyword,
                        "page": page,
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "items": items,
                    },
                    ensure_ascii=False,
                ).encode()

                uri, sha1 = await self.save_raw(
                    raw,
                    "json",
                    content_type="application/json",
                    meta={"keyword": keyword, "page": page},
                )

                # Write outbox row
                from sqlalchemy.dialects.postgresql import insert

                from app.models.ingestion import RawIngestOutbox

                stmt = (
                    insert(RawIngestOutbox)
                    .values(
                        source=self.SOURCE,
                        raw_uri=uri,
                        content_sha1=sha1,
                        content_type="application/json",
                        structured=0,
                        scraper_meta={"keyword": keyword, "page": page, "count": len(items)},
                    )
                    .on_conflict_do_nothing(index_elements=["content_sha1"])
                )
                # Note: no unique constraint on content_sha1 — use the raw_uri as dedup key
                await session.execute(stmt)
                await session.commit()

                total_saved += len(items)
                log.info("etimad_page_fetched", keyword=keyword, page=page, count=len(items))

                # Stop if we got fewer than a full page
                if len(items) < _PAGE_SIZE:
                    break
                page += 1

        log.info("etimad_scrape_done", total_items=total_saved)
        return total_saved


async def run_etimad_scraper() -> None:
    """Entry point for APScheduler."""
    from app.core.database import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        scraper = EtimadScraper()
        await scraper.scrape(session)


async def extract_from_blob(
    session: AsyncSession,
    raw_bytes: bytes,
    outbox_row: RawIngestOutbox,
) -> None:
    """Extract Tender rows from a stored Etimad JSON blob."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.market import Tender

    payload = json.loads(raw_bytes.decode())
    items = payload.get("items", [])

    for item in items:
        etimad_id = str(
            item.get("tenderIdString")
            or item.get("tenderId")
            or item.get("id")
            or hashlib.sha1(json.dumps(item, sort_keys=True).encode()).hexdigest()[:20]
        )

        # Parse published_at
        published_at: datetime | None = None
        for field in ("publishDate", "publish_date", "publishedAt", "createdAt"):
            raw_date = item.get(field)
            if raw_date:
                with contextlib.suppress(ValueError):
                    published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                break

        # Parse deadline_at
        deadline_at: datetime | None = None
        for field in ("lastOfferDate", "last_offer_date", "deadlineAt", "closingDate"):
            raw_date = item.get(field)
            if raw_date:
                with contextlib.suppress(ValueError):
                    deadline_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                break

        # Parse value
        value_sar: float | None = None
        for field in ("tenderValue", "tender_value", "estimatedValue", "value"):
            v = item.get(field)
            if v is not None:
                with contextlib.suppress(TypeError, ValueError):
                    value_sar = float(v)
                break

        stmt = (
            pg_insert(Tender)
            .values(
                etimad_id=etimad_id,
                entity_name=item.get("agencyName")
                or item.get("entityName")
                or item.get("entity_name"),
                title_ar=item.get("tenderName") or item.get("title_ar") or item.get("title"),
                title_en=item.get("tenderNameEn") or item.get("title_en"),
                value_sar=value_sar,
                published_at=published_at,
                deadline_at=deadline_at,
                raw_json=item,
                raw_uri=outbox_row.raw_uri,
            )
            .on_conflict_do_update(
                index_elements=["etimad_id"],
                set_={
                    "entity_name": item.get("agencyName") or item.get("entityName"),
                    "title_ar": item.get("tenderName") or item.get("title_ar"),
                    "title_en": item.get("tenderNameEn") or item.get("title_en"),
                    "value_sar": value_sar,
                    "deadline_at": deadline_at,
                    "raw_json": item,
                },
            )
        )
        await session.execute(stmt)

    await session.commit()
    log.info("etimad_extracted", count=len(items), outbox_id=outbox_row.id)
