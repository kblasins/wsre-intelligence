"""News scraper — multi-source Saudi real estate and business news.

Sources (as of 2026-04):
  argaam_en       argaam.com/en/realestate     — Saudi financial news, English
  argaam_ar       argaam.com/ar/realestate     — Saudi financial news, Arabic
  logistics_me    logisticsmiddleeast.com RSS  — Logistics trade press, RSS feed

Dropped (2026-04 audit):
  - tagid/193 Argaam paths → dead 404
  - saudigazette.com.sa/section/BUSINESS → dead 404
  - arabnews.com/taxonomy/term/10 → dead 404
  - MEED → paywalled SPA, not viable
  - Zawya → full Next.js SPA, no RSS
  - saudi_gazette (saudigazette.com.sa/business): 1/24 articles passed triage (4.2%);
    no dedicated real estate section exists in site navigation; dropped 2026-04-24
  - arab_news (arabnews.com/saudiarabia + /business-economy): 0/29 passed (max score
    0.150); content is general Middle East news (Iran, Russia, sport); no narrower
    real estate section available; dropped 2026-04-24

Known fragilities:
  - Source concentration: ~79% of passing articles come from argaam_ar. If Argaam
    changes their HTML structure or rate-limits, pipeline output drops sharply.
    Mitigation: add a dedicated real-estate RSS source when one is identified.

ToS notes:
  - Scraping public listing/section pages only; no authenticated content
  - Polite rate: ≤1 rps across all sources (sequential with 3-second delay)
  - Full article bodies NOT stored here; news_body fetcher handles those separately
  - Copyright discipline: titles, dates, URLs, summaries only at this stage
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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

NEWS_SOURCES: list[dict[str, str]] = [
    {
        "key": "argaam_en",
        "display": "Argaam (English)",
        "url": "https://www.argaam.com/en/realestate",
        "lang": "en",
        "parser": "argaam",
    },
    {
        "key": "argaam_ar",
        "display": "Argaam (Arabic)",
        "url": "https://www.argaam.com/ar/realestate",
        "lang": "ar",
        "parser": "argaam",
    },
    {
        "key": "logistics_me",
        "display": "Logistics Middle East",
        "url": "https://www.logisticsmiddleeast.com/feed",
        "lang": "en",
        "parser": "rss",
    },
]

_ARGAAM_BASE = "https://www.argaam.com"


async def run_news_scraper() -> None:
    if not settings.scraper_live_mode:
        log.info("news_scraper_skipped", reason="SCRAPER_LIVE_MODE=false")
        return

    scraper = NewsScraper()
    total = 0
    for source in NEWS_SOURCES:
        try:
            count = await scraper.scrape_source(source)
            total += count
            log.info("news_source_done", source=source["key"], count=count)
        except Exception as exc:
            log.warning("news_source_failed", source=source["key"], error=str(exc))

    log.info("news_scraper_done", total_articles=total)


class NewsScraper(BaseScraper):
    SOURCE = "news"

    async def scrape_source(self, source: dict[str, str]) -> int:
        raw_bytes = (await self._http_get(source["url"])).encode()
        uri, sha1 = await self.save_raw(
            raw_bytes, "html", content_type="text/html",
            meta={"source_key": source["key"]},
        )

        parser = source.get("parser", "generic")
        html = raw_bytes.decode(errors="replace")

        if parser == "argaam":
            articles = _parse_argaam(html, source, uri)
        elif parser == "rss":
            articles = _parse_rss(html, source, uri)
        else:
            articles = _parse_generic(html, source, uri)

        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            outbox_row = RawIngestOutbox(
                source="news",
                raw_uri=uri,
                content_sha1=sha1,
                content_type="text/html",
                structured=0,
                scraper_meta={"source_key": source["key"], "url": source["url"]},
            )
            session.add(outbox_row)
            await session.flush()
            count = await _upsert_articles(session, articles)
            outbox_row.structured = 1
            outbox_row.structured_at = datetime.now(UTC)
            await session.commit()

        return count


# ── Per-source parsers ─────────────────────────────────────────────────────────


def _parse_argaam(html: str, source: dict[str, str], raw_uri: str) -> list[dict[str, Any]]:
    """Parse Argaam /realestate section page.

    Articles are linked as <a href="/en/article/articledetail/id/{N}">Title</a>.
    Dates are not reliably associated with each article on the list page, so we
    leave published_at=None and rely on the body fetcher + LLM extraction.
    """
    tree = HTMLParser(html)
    lang = source["lang"]
    seen: set[str] = set()
    articles: list[dict[str, Any]] = []

    for a in tree.css("a"):
        href = (a.attrs.get("href") or "").strip()
        if "/articledetail/id/" not in href:
            continue
        title = a.text(strip=True)
        if not title or len(title) < 8:
            continue
        # deduplicate by href
        if href in seen:
            continue
        seen.add(href)

        # Extract numeric article ID as external_id
        m = re.search(r"/id/(\d+)", href)
        external_id = m.group(1) if m else href.split("/")[-1]

        article: dict[str, Any] = {
            "source": source["key"],
            "external_id": external_id,
            "url": f"{_ARGAAM_BASE}{href}" if href.startswith("/") else href,
            "published_at": None,
            "raw_uri": raw_uri,
            "extracted_at": datetime.now(UTC),
            "structured_facts": {},
            "relevance_score": None,
        }
        if lang == "ar":
            article["title_ar"] = title
        else:
            article["title_en"] = title
        articles.append(article)

    return articles


def _parse_rss(rss_text: str, source: dict[str, str], raw_uri: str) -> list[dict[str, Any]]:
    """Parse a standard RSS 2.0 feed."""
    articles: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as exc:
        log.warning("rss_parse_error", source=source["key"], error=str(exc))
        return articles

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_str = item.findtext("pubDate") or ""

        if not title or len(title) < 8 or not link:
            continue

        published_at: datetime | None = None
        if pub_date_str:
            try:
                published_at = parsedate_to_datetime(pub_date_str).astimezone(UTC).replace(tzinfo=UTC)
            except Exception:
                pass

        external_id = link.rstrip("/").split("/")[-1] or title[:80]

        articles.append({
            "source": source["key"],
            "external_id": external_id,
            "title_en": title,
            "url": link,
            "published_at": published_at,
            "raw_uri": raw_uri,
            "extracted_at": datetime.now(UTC),
            "structured_facts": {},
            "relevance_score": None,
        })

    return articles


def _parse_generic(html: str, source: dict[str, str], raw_uri: str) -> list[dict[str, Any]]:
    """Generic fallback parser."""
    tree = HTMLParser(html)
    articles: list[dict[str, Any]] = []
    lang = source["lang"]
    base_url = "/".join(source["url"].split("/")[:3])

    for item in tree.css("article, .article, .news-item, h2, h3"):
        try:
            link_el = item.css_first("a[href]")
            if not link_el:
                continue
            title = link_el.text(strip=True)
            if not title or len(title) < 10:
                continue
            href = (link_el.attrs.get("href") or "")
            if not href:
                continue
            url = href if href.startswith("http") else f"{base_url}{href}"
            external_id = href.rstrip("/").split("/")[-1] or title[:80]
            date_el = item.css_first("time,[class*='date']")
            article: dict[str, Any] = {
                "source": source["key"],
                "external_id": external_id,
                "url": url,
                "published_at": _parse_date(
                    (date_el.attrs.get("datetime") if date_el else None)
                    or (date_el.text(strip=True) if date_el else None)
                ),
                "raw_uri": raw_uri,
                "extracted_at": datetime.now(UTC),
                "structured_facts": {},
                "relevance_score": None,
            }
            if lang == "ar":
                article["title_ar"] = title
            else:
                article["title_en"] = title
            articles.append(article)
        except Exception:
            continue

    return articles


# ── DB helpers ────────────────────────────────────────────────────────────────


async def _upsert_articles(session: AsyncSession, articles: list[dict[str, Any]]) -> int:
    count = 0
    for article in articles:
        stmt = (
            insert(NewsArticle)
            .values(**article)
            .on_conflict_do_update(
                constraint="uq_article_source_external_id",
                set_={"extracted_at": article["extracted_at"]},
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
    source_key = outbox_row.scraper_meta.get("source_key", "argaam_en")
    source = next((s for s in NEWS_SOURCES if s["key"] == source_key), NEWS_SOURCES[0])
    html = raw_bytes.decode(errors="replace")
    parser = source.get("parser", "generic")
    if parser == "argaam":
        articles = _parse_argaam(html, source, outbox_row.raw_uri)
    elif parser == "rss":
        articles = _parse_rss(html, source, outbox_row.raw_uri)
    else:
        articles = _parse_generic(html, source, outbox_row.raw_uri)
    await _upsert_articles(session, articles)


# ── Date helpers ──────────────────────────────────────────────────────────────


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip()[:19], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    asyncio.run(run_news_scraper())
