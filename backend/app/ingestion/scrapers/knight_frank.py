"""Knight Frank PDF report scraper.

Strategy: direct PDF GET from Knight Frank's public research portal.
Copyright note: PDFs are downloaded for internal intelligence use only.
They are NOT redistributed. The system extracts facts (rent figures, transaction
counts, forecasts) and cites the source — it does not reproduce the reports.

ToS risk: MEDIUM (copyright). Mitigated by:
  - Not redistributing the PDFs
  - Citing the source on every extracted fact
  - Using only published, publicly accessible reports

PDF extraction pipeline (Phase 2):
  1. pymupdf4llm → Markdown (fast, free, handles most pages)
  2. Azure Document Intelligence Layout (for complex tables flagged by a classifier)
  3. Claude Sonnet 4.6 vision fallback (for garbled Arabic RTL pages)

This Phase 1 scraper only downloads and stores the PDF blobs. Extraction
(structured facts → transactions, rent_index rows) happens in Phase 2.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.ingestion.base import BaseScraper
from app.models.ingestion import RawIngestOutbox

log = structlog.get_logger(__name__)

# Known Knight Frank Riyadh / KSA Industrial report URLs.
# These are publicly indexed — add new reports as they are published.
# Format: (url, report_slug, quarter, year)
KNOWN_REPORTS: list[dict[str, Any]] = [
    {
        "url": "https://content.knightfrank.com/research/2024/articles/en/saudi-arabia-industrial-market-report-2024-11741.pdf",
        "slug": "kf-ksa-industrial-2024",
        "source_priority": 2,
    },
    # Add new reports here as they are published (quarterly cadence)
]

# CBRE and JLL reports follow the same pattern — add when URLs are known
CBRE_REPORTS: list[dict[str, Any]] = []
JLL_REPORTS: list[dict[str, Any]] = []


async def run_reports_scraper() -> None:
    """Download all known research PDFs and store blobs for Phase 2 extraction."""
    if not settings.scraper_live_mode:
        log.info("reports_scraper_skipped", reason="SCRAPER_LIVE_MODE=false")
        return

    all_reports = KNOWN_REPORTS + CBRE_REPORTS + JLL_REPORTS
    scraper = ReportScraper()

    downloaded = 0
    for report in all_reports:
        try:
            result = await scraper.download_report(report)
            if result:
                downloaded += 1
        except Exception as exc:
            log.warning("report_download_failed", url=report["url"], error=str(exc))

    log.info("reports_scraper_done", downloaded=downloaded, total=len(all_reports))


class ReportScraper(BaseScraper):
    SOURCE = "knight_frank"

    async def download_report(self, report: dict[str, Any]) -> bool:
        """Download one PDF, store blob, create outbox row for Phase 2 extraction.

        Returns True if downloaded (or already exists in storage), False on error.
        """
        url = report["url"]
        slug = report["slug"]

        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0; +https://whitestar.sa/intelligence)",
                "Accept": "application/pdf",
            },
            timeout=60,
            follow_redirects=True,
        ) as client:
            log.info("report_downloading", slug=slug, url=url)
            resp = await client.get(url)
            if resp.status_code == 404:
                log.warning("report_not_found", slug=slug, url=url)
                return False
            resp.raise_for_status()

            pdf_bytes = resp.content
            if not pdf_bytes.startswith(b"%PDF"):
                log.warning(
                    "report_not_pdf", slug=slug, content_type=resp.headers.get("content-type")
                )
                return False

        uri, sha1 = await self.save_raw(pdf_bytes, "pdf", content_type="application/pdf")

        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            outbox_row = RawIngestOutbox(
                source=self.SOURCE,
                raw_uri=uri,
                content_sha1=sha1,
                content_type="application/pdf",
                structured=0,  # Phase 2 will extract structured facts
                scraper_meta={
                    "slug": slug,
                    "url": url,
                    "source_priority": report.get("source_priority", 2),
                    "size_bytes": len(pdf_bytes),
                },
            )
            session.add(outbox_row)
            await session.commit()

        log.info("report_stored", slug=slug, uri=uri, size_kb=len(pdf_bytes) // 1024)
        return True


if __name__ == "__main__":
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    asyncio.run(run_reports_scraper())
