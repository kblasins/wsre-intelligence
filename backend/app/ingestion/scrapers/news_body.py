"""Article body fetcher — fills body_en / body_ar for high-relevance articles.

After triage scores articles ≥ 0.5, this fetcher visits each article URL
and extracts the full body text. Sonnet extraction quality improves
dramatically with a full body vs title-only.

Run order in the LLM pipeline:
  1. news.py scraper   → titles only, relevance_score=NULL
  2. news extractor    → Haiku triage (relevance_score populated)
  3. news_body.py      → fetch body for relevance ≥ 0.5       ← this file
  4. news extractor    → Sonnet extraction (now has body)

Entry point: run_news_body_fetcher()
APScheduler: runs every 2 hours, after triage but before extraction.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime

import httpx
import structlog
from selectolax.parser import HTMLParser
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.models.market import NewsArticle

log = structlog.get_logger(__name__)

BATCH_SIZE = 30
REQUEST_DELAY = (1.0, 2.5)  # seconds between requests (polite rate)
TIMEOUT = 20

# Per-source body extraction selectors — most specific first
_SELECTORS: dict[str, list[str]] = {
    "argaam_en": [
        "[class*='article-content']",
        "[class*='articleBody']",
        ".article-text",
        "article p",
    ],
    "argaam_ar": [
        "[class*='article-content']",
        "[class*='articleBody']",
        ".article-text",
        "article p",
    ],
    "modon": [
        ".ms-rtestate-field",
        ".sitecore-content",
        "article",
        ".page-content p",
    ],
    "saudi_gazette": [
        ".article-body",
        "[class*='article-body']",
        ".field-body",
        "article p",
    ],
    "arab_news": [
        ".article-body",
        "[class*='article__body']",
        ".article-content",
        "article p",
    ],
    # Polish sources
    "eurobuild_cee": [
        ".article__body",
        ".article-body",
        "[class*='article-content']",
        "[class*='articleContent']",
        ".entry-content",
        "article .content",
        "article p",
    ],
    "inwestycje_pl": [
        ".article__body",
        ".article-body",
        ".entry-content",
        "[class*='article-content']",
        "article .content",
        "article p",
    ],
}
_DEFAULT_SELECTORS = [
    "article",
    "[class*='article-body']",
    "[class*='article-content']",
    "[class*='content-body']",
    "main p",
]


def _extract_body(html: str, source: str) -> str:
    """Extract main article text from HTML using source-specific selectors."""
    tree = HTMLParser(html)

    selectors = _SELECTORS.get(source, []) + _DEFAULT_SELECTORS
    for sel in selectors:
        nodes = tree.css(sel)
        if not nodes:
            continue
        text = " ".join(n.text(strip=True) for n in nodes if n.text(strip=True))
        if len(text) > 200:  # at least 200 chars = real content
            return text[:8000]  # cap body at 8000 chars

    # Fallback: all <p> tags
    paras = tree.css("p")
    text = " ".join(p.text(strip=True) for p in paras if len(p.text(strip=True)) > 30)
    return text[:8000]


def _extract_published_at(html: str) -> datetime | None:
    """Best-effort extraction of article publish date from HTML.

    Tries structured metadata first (most reliable), then visible date elements.
    Returns a timezone-aware datetime in UTC, or None if not found.
    """
    import re
    from email.utils import parsedate_to_datetime

    tree = HTMLParser(html)

    # 1. <meta property="article:published_time" content="2026-04-20T10:30:00Z">
    for meta in tree.css('meta[property="article:published_time"], meta[name="publish-date"], meta[name="date"]'):
        val = meta.attrs.get("content", "")
        if val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.astimezone(UTC)
            except ValueError:
                pass

    # 2. <time datetime="...">
    for time_el in tree.css("time[datetime]"):
        val = time_el.attrs.get("datetime", "")
        if val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.astimezone(UTC)
            except ValueError:
                pass

    # 3. JSON-LD datePublished
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            import json
            data = json.loads(script.text())
            if isinstance(data, list):
                data = data[0]
            pub = data.get("datePublished") or data.get("uploadDate")
            if pub:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                return dt.astimezone(UTC)
        except Exception:
            pass

    # 4. RFC 2822 date in visible date elements
    for sel in ['[class*="date"]', '[class*="time"]', '[class*="publish"]', "span.date", ".article-date"]:
        for el in tree.css(sel):
            txt = el.text(strip=True)
            if txt:
                try:
                    dt = parsedate_to_datetime(txt)
                    return dt.astimezone(UTC)
                except Exception:
                    pass
                # ISO-like pattern
                m = re.search(r"(\d{4}-\d{2}-\d{2})", txt)
                if m:
                    try:
                        dt = datetime.fromisoformat(m.group(1))
                        return dt.replace(tzinfo=UTC)
                    except ValueError:
                        pass

    return None


async def _fetch_body(client: httpx.AsyncClient, article: NewsArticle) -> tuple[str | None, datetime | None]:
    """Fetch article detail page. Returns (body_text, published_at) — either may be None."""
    if not article.url:
        return None, None
    try:
        resp = await client.get(article.url, follow_redirects=True)
        if resp.status_code != 200:
            log.debug("body_fetch_non200", url=article.url, status=resp.status_code)
            return None, None
        body = _extract_body(resp.text, article.source)
        pub_at = _extract_published_at(resp.text) if article.published_at is None else None
        return body or None, pub_at
    except Exception as exc:
        log.debug("body_fetch_failed", article_id=article.id, error=str(exc)[:100])
        return None, None


async def run_news_body_fetcher() -> int:
    """Fetch bodies for relevant articles that are missing them.

    Returns number of articles updated.
    """
    if not settings.scraper_live_mode:
        log.info("news_body_fetcher_skipped", reason="SCRAPER_LIVE_MODE=false")
        return 0

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(NewsArticle)
            .where(
                NewsArticle.relevance_score >= 0.35,
                NewsArticle.body_en.is_(None),
                NewsArticle.body_ar.is_(None),
                NewsArticle.url.is_not(None),
            )
            .order_by(NewsArticle.relevance_score.desc())
            .limit(BATCH_SIZE)
        )
        articles = list(result.scalars())

    if not articles:
        log.info("news_body_fetcher_nothing_to_fetch")
        return 0

    log.info("news_body_fetcher_start", count=len(articles))
    updated = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    proxy = str(settings.ksa_proxy_url) if settings.ksa_proxy_url else None

    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT, proxy=proxy) as client:
        for article in articles:
            body, pub_at = await _fetch_body(client, article)
            if not body and pub_at is None:
                await asyncio.sleep(random.uniform(*REQUEST_DELAY))
                continue

            # Store in the appropriate language column
            lang_col = "body_ar" if article.source.endswith("_ar") else "body_en"
            values: dict = {"extracted_at": datetime.now(UTC)}
            if body:
                values[lang_col] = body
            if pub_at is not None:
                values["published_at"] = pub_at
            async with AsyncSessionFactory() as session:
                await session.execute(
                    update(NewsArticle)
                    .where(NewsArticle.id == article.id)
                    .values(**values)
                )
                await session.commit()

            updated += 1
            log.debug(
                "body_fetched",
                article_id=article.id,
                lang=lang_col,
                chars=len(body) if body else 0,
                published_at=pub_at.isoformat() if pub_at else None,
            )
            await asyncio.sleep(random.uniform(*REQUEST_DELAY))

    log.info("news_body_fetcher_done", updated=updated, total=len(articles))
    return updated


if __name__ == "__main__":
    import asyncio as _asyncio

    from app.core.logging import configure_logging

    configure_logging()
    _asyncio.run(run_news_body_fetcher())
