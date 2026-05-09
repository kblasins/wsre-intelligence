"""MODON news scraper.

MODON's portal (modon.gov.sa) is SharePoint-based with no RSS feed or JSON API.
News cadence is weeks-to-months — daily scraping is sufficient.

ToS risk: LOW for public marketing pages.
Higher-frequency signal (announcements, new city openings) comes from X @modon_ksa
and LinkedIn — those are Phase 2 if needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from selectolax.parser import HTMLParser
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.ingestion.base import BaseScraper
from app.models.ingestion import RawIngestOutbox
from app.models.market import NewsArticle

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

NEWS_URL = "https://www.modon.gov.sa/en/MediaCenter/modon-news/News/Pages/default.aspx"
SOURCE = "modon"


async def run_modon_scraper() -> None:
    if not settings.scraper_live_mode:
        log.info("modon_scraper_skipped", reason="SCRAPER_LIVE_MODE=false")
        return

    scraper = ModonScraper()
    await scraper.run()


class ModonScraper(BaseScraper):
    SOURCE = "modon"

    async def run(self) -> None:
        html = await self._http_get(NEWS_URL)
        raw_bytes = html.encode()
        uri, sha1 = await self.save_raw(raw_bytes, "html")

        articles = _parse_news_page(html, uri)

        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            outbox_row = RawIngestOutbox(
                source=self.SOURCE,
                raw_uri=uri,
                content_sha1=sha1,
                content_type="text/html",
                structured=0,
                scraper_meta={"url": NEWS_URL},
            )
            session.add(outbox_row)
            await session.flush()

            count = await _upsert_articles(session, articles)

            outbox_row.structured = 1
            outbox_row.structured_at = datetime.now(UTC)
            await session.commit()

        log.info("modon_scraper_done", articles=count)


def _parse_news_page(html: str, raw_uri: str) -> list[dict[str, Any]]:
    tree = HTMLParser(html)
    articles = []
    for item in tree.css(".ms-WPBody li, .news-item, [class*='newsItem']"):
        try:
            title_el = item.css_first("a, h3, h4")
            date_el = item.css_first(".date, [class*='date'], time")
            link_el = item.css_first("a[href]")

            if not title_el:
                continue

            title = title_el.text(strip=True)
            if not title:
                continue

            href = link_el.attributes.get("href", "") if link_el else ""
            external_id = href or title[:100]

            articles.append(
                {
                    "source": SOURCE,
                    "external_id": external_id,
                    "title_en": title,
                    "url": f"https://www.modon.gov.sa{href}" if href.startswith("/") else href,
                    "published_at": _parse_date(date_el.text(strip=True) if date_el else None),
                    "raw_uri": raw_uri,
                    "extracted_at": datetime.now(UTC),
                    "structured_facts": {},
                }
            )
        except Exception:
            continue
    return articles


async def _upsert_articles(session: AsyncSession, articles: list[dict[str, Any]]) -> int:
    count = 0
    for article in articles:
        stmt = (
            insert(NewsArticle)
            .values(**article)
            .on_conflict_do_update(
                constraint="uq_article_source_external_id",
                set_={"title_en": article["title_en"], "extracted_at": article["extracted_at"]},
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
    articles = _parse_news_page(raw_bytes.decode(errors="replace"), outbox_row.raw_uri)
    await _upsert_articles(session, articles)


if __name__ == "__main__":
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    asyncio.run(run_modon_scraper())


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%d %b %Y", "%d/%m/%Y", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
