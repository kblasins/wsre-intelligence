"""Polish real estate news scrapers.

Sources:
  eurobuild_cee    eurobuildcee.com/en/news/rss  English CEE trade press — via RSS feed
  inwestycje_pl    inwestycje.pl/nieruchomosci/  Polish financial news, RE section

Scraping policy:
  - Public listing/section pages + RSS only — no authenticated content
  - Rate: 1 request per 2 seconds (0.5 rps)
  - User-Agent: WSRE Intelligence Research Crawler
  - Pagination: up to MAX_PAGES pages for HTML sources
  - Raw blobs saved before parsing (raw-first pattern from base.py)

Source selection rationale:
  - eurobuild_cee: strongest English-language Warsaw office + capital markets desk in CEE;
    RSS feed is stable, clean, and gives full dates
  - inwestycje_pl: Warsaw-focused Polish financial news; article links are reliably structured
    in <article><h2><a> with slugged hrefs; paginated via ?page=N
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any

import structlog

from app.core.config import settings
from app.ingestion.base import BaseScraper
from app.ingestion.scrapers.news import _upsert_articles
from app.models.ingestion import RawIngestOutbox

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

POLISH_NEWS_SOURCES: list[dict[str, Any]] = [
    {
        "key": "eurobuild_cee",
        "display": "Eurobuild CEE",
        "base_url": "https://eurobuildcee.com",
        "index_url": "https://eurobuildcee.com/en/news/rss",
        "lang": "en",
        "parser": "rss",
        "max_pages": 1,   # RSS gives 50 items at once
    },
    {
        "key": "inwestycje_pl",
        "display": "Inwestycje.pl Nieruchomości",
        "base_url": "https://inwestycje.pl",
        "index_url": "https://inwestycje.pl/nieruchomosci/",
        "lang": "pl",
        "parser": "inwestycje_pl",
        "page_param": "page",
        "max_pages": 8,   # ~24 articles/page → 192 articles max
    },
]

_CRAWLER_UA = "WSRE Intelligence Research Crawler / hello@wsre-intelligence.pl"
_REQUEST_DELAY = 2.0    # seconds between HTTP requests
_LOOKBACK_DAYS = 30     # ignore articles older than this


async def run_polish_news_scraper() -> dict[str, int]:
    """Scrape all Polish news sources. Returns {source_key: article_count}.

    Requires SCRAPER_LIVE_MODE=true in settings.
    """
    if not settings.scraper_live_mode:
        log.info("polish_news_scraper_skipped", reason="SCRAPER_LIVE_MODE=false")
        return {}

    scraper = PolishNewsScraper()
    results: dict[str, int] = {}

    for source in POLISH_NEWS_SOURCES:
        try:
            count = await scraper.scrape_source(source)
            results[source["key"]] = count
            log.info("polish_source_done", source=source["key"], articles=count)
        except Exception as exc:
            log.warning("polish_source_failed", source=source["key"], error=str(exc))
            results[source["key"]] = 0

    log.info("polish_news_scraper_done", total=sum(results.values()), per_source=results)
    return results


class PolishNewsScraper(BaseScraper):
    SOURCE = "polish_news"

    async def scrape_source(self, source: dict[str, Any]) -> int:
        """Scrape up to max_pages pages of a Polish news source."""
        import httpx

        headers = {
            "User-Agent": _CRAWLER_UA,
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        all_articles: list[dict[str, Any]] = []
        cutoff = datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)
        stop_early = False

        async with httpx.AsyncClient(
            headers=headers,
            timeout=30,
            follow_redirects=True,
        ) as client:
            for page_num in range(1, source["max_pages"] + 1):
                if stop_early:
                    break

                page_url = source["index_url"]
                if page_num > 1 and source.get("page_param"):
                    param = source["page_param"]
                    sep = "&" if "?" in page_url else "?"
                    page_url = f"{page_url}{sep}{param}={page_num}"

                try:
                    resp = await client.get(page_url)
                    if resp.status_code != 200:
                        log.warning(
                            "polish_page_non200",
                            source=source["key"], page=page_num, status=resp.status_code,
                        )
                        break
                    raw_bytes = resp.content
                    html = resp.text
                except Exception as exc:
                    log.warning(
                        "polish_page_fetch_failed",
                        source=source["key"], page=page_num, error=str(exc)[:120],
                    )
                    break

                # Save raw blob
                uri, _sha1 = await self.save_raw(
                    raw_bytes, "html",
                    content_type="text/html",
                    meta={"source_key": source["key"], "page": page_num, "url": page_url},
                )

                parser_name = source.get("parser", "generic")
                if parser_name == "rss":
                    articles = _parse_rss_eurobuild(html, source, uri, cutoff)
                    stop_early = True  # RSS gives all recent articles at once
                elif parser_name == "inwestycje_pl":
                    articles, reached_cutoff = _parse_inwestycje_pl(html, source, uri, cutoff)
                    if reached_cutoff:
                        stop_early = True
                else:
                    log.warning("unknown_parser", parser=parser_name, source=source["key"])
                    break

                if not articles:
                    log.info("polish_page_empty", source=source["key"], page=page_num)
                    break

                all_articles.extend(articles)
                log.debug(
                    "polish_page_scraped",
                    source=source["key"], page=page_num,
                    count=len(articles), total=len(all_articles),
                )

                if page_num < source["max_pages"] and not stop_early:
                    await asyncio.sleep(_REQUEST_DELAY)

        if not all_articles:
            return 0

        # Deduplicate by (source, external_id)
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for a in all_articles:
            key = (a["source"], a["external_id"])
            if key not in seen:
                seen.add(key)
                unique.append(a)

        # Persist to DB via outbox
        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            outbox = RawIngestOutbox(
                source="polish_news",
                raw_uri=f"polish_news/{source['key']}/batch",
                content_sha1="batch",
                content_type="text/html",
                structured=0,
                scraper_meta={"source_key": source["key"]},
            )
            session.add(outbox)
            await session.flush()
            count = await _upsert_articles(session, unique)
            outbox.structured = 1
            outbox.structured_at = datetime.now(UTC)
            await session.commit()

        return count


# ── Per-source parsers ─────────────────────────────────────────────────────────


def _parse_rss_eurobuild(
    rss_text: str,
    source: dict[str, Any],
    raw_uri: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Parse Eurobuild CEE RSS 2.0 feed.

    Feed URL: https://eurobuildcee.com/en/news/rss
    Provides clean titles, URLs, and pubDate — no HTML noise.
    Articles older than `cutoff` are excluded.
    """
    articles: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as exc:
        log.warning("eurobuild_rss_parse_error", error=str(exc))
        return articles

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_str = (item.findtext("pubDate") or "").strip()

        if not title or len(title) < 8 or not link:
            continue

        published_at: datetime | None = None
        if pub_date_str:
            try:
                published_at = parsedate_to_datetime(pub_date_str).astimezone(UTC)
            except Exception:
                pass

        # Enforce lookback window on dated articles
        if published_at and published_at < cutoff:
            continue

        # External ID from URL slug (e.g. 36486-aupark-refinanced → 36486)
        m = re.search(r"/(\d+)-", link)
        external_id = m.group(1) if m else link.rstrip("/").split("/")[-1][:80]

        articles.append({
            "source": source["key"],
            "external_id": external_id,
            "title_en": title,
            "url": link,
            "published_at": published_at,
            "raw_uri": raw_uri,
            "extracted_at": now,
            "structured_facts": {},
            "relevance_score": None,
        })

    log.debug("eurobuild_rss_parsed", count=len(articles))
    return articles


def _parse_inwestycje_pl(
    html: str,
    source: dict[str, Any],
    raw_uri: str,
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], bool]:
    """Parse inwestycje.pl/nieruchomosci/ listing page.

    Article structure:
      <article>
        <h2><a href="/nieruchomosci/{slug}">Title text</a></h2>
        <time datetime="YYYY-MM-DD">DD.MM.YYYY</time>  (if present)
      </article>

    Returns (articles, reached_cutoff).
    """
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    base_url = source["base_url"]
    articles: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    reached_cutoff = False
    seen_hrefs: set[str] = set()

    # Primary selector: <article> blocks containing <a href="/nieruchomosci/...">
    # Fallback: any h2/h3 link to /nieruchomosci/
    selectors = [
        "article h2 a, article h3 a",
        "h2 a[href*='/nieruchomosci/'], h3 a[href*='/nieruchomosci/']",
    ]

    candidates: list[tuple[str, str, datetime | None]] = []

    for selector in selectors:
        for a in tree.css(selector):
            href = (a.attrs.get("href") or "").strip()
            if not href:
                continue
            # Require article-like URL (not category page)
            if not _is_inwestycje_article(href):
                continue
            title = a.text(strip=True)
            if not title or len(title) < 15:
                continue
            full_url = href if href.startswith("http") else f"{base_url}{href}"
            if full_url in seen_hrefs:
                continue
            seen_hrefs.add(full_url)

            # Try to find a date in the parent article element
            pub_at: datetime | None = None
            try:
                parent = a.parent
                for _ in range(4):  # walk up
                    if parent is None:
                        break
                    time_el = parent.css_first("time[datetime], time")
                    if time_el:
                        dt_val = time_el.attrs.get("datetime") or time_el.text(strip=True)
                        if dt_val:
                            pub_at = _parse_date_pl(dt_val)
                            if pub_at:
                                break
                    parent = parent.parent
            except Exception:
                pass

            if pub_at and pub_at < cutoff:
                reached_cutoff = True
                continue  # skip old articles but keep checking for newer ones

            candidates.append((full_url, title, pub_at))

        if candidates:
            break  # use first selector that yields results

    for full_url, title, pub_at in candidates:
        # Extract numeric/slug ID from URL
        # URL pattern: /nieruchomosci/slug-text or /nieruchomosci/category/slug
        slug = full_url.rstrip("/").split("/")[-1]
        external_id = slug[:120]

        articles.append({
            "source": source["key"],
            "external_id": external_id,
            "title_en": title,    # Polish stored in _en field (no _pl column in schema)
            "url": full_url,
            "published_at": pub_at,
            "raw_uri": raw_uri,
            "extracted_at": now,
            "structured_facts": {},
            "relevance_score": None,
        })

    return articles, reached_cutoff


def _is_inwestycje_article(href: str) -> bool:
    """Return True if the href looks like an individual article, not a section page."""
    # Reject short paths like /nieruchomosci/ (section index)
    path = href.split("?")[0].rstrip("/")
    segs = [s for s in path.split("/") if s]
    if len(segs) < 2:
        return False
    last = segs[-1]
    # Article slugs are typically long with hyphens or contain numbers
    return len(last) > 10 and ("-" in last or any(c.isdigit() for c in last))


def _parse_date_pl(value: str) -> datetime | None:
    """Parse Polish/ISO date strings."""
    if not value:
        return None
    value = value.strip()
    # ISO format: 2026-05-08 or 2026-05-08T10:00:00
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:19], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
