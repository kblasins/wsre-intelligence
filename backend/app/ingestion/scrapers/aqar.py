"""Aqar.fm warehouse listing scraper.

Aqar is the largest KSA listing portal (50M+ visits, 1.5M+ listings, REGA-licensed).
Warehouse listings URL pattern: sa.aqar.fm/en/warehouse-for-rent/{city}/{district}

Bot protection: Cloudflare WAF with REQ_DEVICE_TOKEN, cf_clearance, __cf_bm cookies.
Approach: httpx with saved CF cookies + Playwright fallback when CF challenges block.

ToS risk: MEDIUM-HIGH. Aqar is REGA-licensed which adds Real Estate Brokerage Law
constraints on downstream data use. Data is used for market intelligence only,
not for soliciting clients or replicating the listing database.

Rate limit: ≤1 req/sec, single session, KSA residential proxy if available.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from selectolax.parser import HTMLParser
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.ingestion.base import EXTRACTOR_VERSION, BaseScraper
from app.models.ingestion import RawIngestOutbox
from app.models.market import Listing

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

PORTAL = "aqar"
BASE_URL = "https://sa.aqar.fm"
STATE_FILE = Path(settings.playwright_state_dir) / "aqar_state.json"

# Priority Riyadh industrial districts for warehouse tracking.
# Full list ordered by data priority; first 3 are used in test/manual runs.
TARGET_DISTRICTS: list[dict[str, str]] = [
    {"slug": "riyadh/industrial-city", "name_en": "Industrial City", "name_ar": "المدينة الصناعية"},
    {
        "slug": "riyadh/second-industrial-city",
        "name_en": "2nd Industrial City",
        "name_ar": "المدينة الصناعية الثانية",
    },
    {
        "slug": "riyadh/third-industrial-city",
        "name_en": "3rd Industrial City",
        "name_ar": "المدينة الصناعية الثالثة",
    },
    {"slug": "riyadh/olaya", "name_en": "Olaya", "name_ar": "العليا"},
    {"slug": "riyadh/north-riyadh", "name_en": "North Riyadh", "name_ar": "شمال الرياض"},
    {"slug": "riyadh/east-riyadh", "name_en": "East Riyadh", "name_ar": "شرق الرياض"},
    # Added 2026-04-24: Riyadh eastern/southern logistics corridors
    {"slug": "riyadh/al-qadisiyah", "name_en": "Al Qadisiyah", "name_ar": "القادسية"},
    {"slug": "riyadh/al-janadriyah", "name_en": "Al Janadriyah", "name_ar": "الجنادرية"},
    {"slug": "riyadh/al-sulay", "name_en": "Al Sulay", "name_ar": "السلي"},
    {"slug": "riyadh/south-riyadh", "name_en": "South Riyadh", "name_ar": "جنوب الرياض"},
]

# Districts used in manual/test runs (scheduler uses all TARGET_DISTRICTS)
_TEST_DISTRICTS = TARGET_DISTRICTS[:3]


async def run_aqar_scraper(districts: list[dict[str, str]] | None = None) -> None:
    """Entry point for APScheduler — scrapes warehouse listings for target districts."""
    if not settings.scraper_live_mode:
        log.info("aqar_scraper_skipped", reason="SCRAPER_LIVE_MODE=false")
        return

    scraper = AqarScraper()
    total = 0
    for district in (districts or TARGET_DISTRICTS):
        try:
            count = await scraper.scrape_district(district)
            total += count
            # Polite rate: 1-2 seconds between district requests
            await _async_sleep(random.uniform(1.0, 2.0))
        except Exception as exc:
            log.warning("aqar_district_failed", district=district["name_en"], error=str(exc))

    log.info("aqar_scraper_done", total_listings=total)


class AqarScraper(BaseScraper):
    SOURCE = "aqar"

    async def scrape_district(self, district: dict[str, str]) -> int:
        """Scrape one district's warehouse-for-rent listings."""
        url = f"{BASE_URL}/en/warehouse-for-rent/{district['slug']}"

        try:
            html = await self._fetch_with_cf_cookies(url)
        except Exception:
            # CF cookie session failed — fall back to Playwright
            log.info("aqar_playwright_fallback", district=district["name_en"])
            html = await self._fetch_with_playwright(url)

        raw_bytes = html.encode()
        uri, sha1 = await self.save_raw(raw_bytes, "html", content_type="text/html")

        listings = _parse_listing_page(html, district, uri)
        if not listings:
            log.info("aqar_no_listings", district=district["name_en"], url=url)
            return 0

        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            outbox_row = RawIngestOutbox(
                source=self.SOURCE,
                raw_uri=uri,
                content_sha1=sha1,
                content_type="text/html",
                structured=0,
                scraper_meta={"district": district["slug"]},
            )
            session.add(outbox_row)
            await session.flush()

            count = await _upsert_listings(session, listings)

            outbox_row.structured = 1
            outbox_row.structured_at = datetime.now(UTC)
            await session.commit()

        log.info("aqar_district_done", district=district["name_en"], listings=count)
        return count

    async def _fetch_with_cf_cookies(self, url: str) -> str:
        """Use httpx with saved Cloudflare cookies."""
        import httpx

        cookies = {}
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            for cookie in state.get("cookies", []):
                if "aqar.fm" in cookie.get("domain", ""):
                    cookies[cookie["name"]] = cookie["value"]

        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
                "Referer": BASE_URL,
            },
            cookies=cookies,
            timeout=20,
            follow_redirects=True,
            proxy=str(settings.ksa_proxy_url) if settings.ksa_proxy_url else None,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 403 or "cf-challenge" in resp.text.lower():
                raise ValueError("Cloudflare challenge detected — needs Playwright")
            resp.raise_for_status()
            # Aqar is a React SPA — a 200 with an empty shell has no listing data.
            # Detect this by checking for __NEXT_DATA__ listings or property card elements.
            if not _html_has_listings(resp.text):
                raise ValueError("SPA shell detected — no listing elements in 200 response, needs Playwright")
            return resp.text

    async def _fetch_with_playwright(self, url: str) -> str:
        """Playwright fallback — handles Cloudflare JS challenges."""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": settings.ksa_proxy_url} if settings.ksa_proxy_url else None,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = await browser.new_context(
                locale="en-US",
                timezone_id="Asia/Riyadh",
                viewport={"width": 1280, "height": 800},
                storage_state=str(STATE_FILE) if STATE_FILE.exists() else None,
            )
            await Stealth().apply_stealth_async(ctx)

            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_timeout(random.randint(1000, 2000))
            html = await page.content()

            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(STATE_FILE))
            await browser.close()

        return html


def _html_has_listings(html: str) -> bool:
    """Return True if HTML contains actual listing data (not just a React SPA shell)."""
    import re

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    if match:
        try:
            next_data = json.loads(match.group(1))
            props = next_data.get("props", {}).get("pageProps", {})
            items = props.get("properties", props.get("listings", props.get("results", [])))
            if items:
                return True
        except Exception:
            pass

    tree = HTMLParser(html)
    if tree.css("[data-testid='property-card'], .property-card, article[class*='propert'], a[href*='warehouse-for-rent-']"):
        return True

    return False


def _parse_listing_page(html: str, district: dict[str, str], raw_uri: str) -> list[dict[str, Any]]:
    """Parse Aqar listing HTML into normalized dicts.

    Aqar uses React SSR — listing data may be in both HTML and a __NEXT_DATA__
    JSON blob. We try __NEXT_DATA__ first (more structured) then fall back to HTML.
    """
    listings: list[dict[str, Any]] = []

    # Try __NEXT_DATA__ JSON blob first
    try:
        import re

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL
        )
        if match:
            next_data = json.loads(match.group(1))
            # Navigate to listing array — path varies by Aqar version
            props = next_data.get("props", {}).get("pageProps", {})
            items = props.get("properties", props.get("listings", props.get("results", [])))
            for item in items:
                listing = _parse_next_data_item(item, district, raw_uri)
                if listing:
                    listings.append(listing)
            if listings:
                return listings
    except Exception as exc:
        log.debug("aqar_next_data_parse_failed", error=str(exc))

    # Fallback: parse HTML with selectolax.
    # Aqar uses Tailwind utility classes — no semantic property-card class.
    # Listing cards are rendered as <a href="/en/warehouse-for-rent/…/warehouse-for-rent-{id}">
    try:
        tree = HTMLParser(html)
        # Primary selector: links whose href ends with "warehouse-for-rent-{id}"
        cards = tree.css('a[href*="warehouse-for-rent-"]')
        if not cards:
            # Broader fallback for other listing types
            cards = tree.css("[data-testid='property-card'], .property-card, article[class*='propert']")
        for card in cards:
            listing = _parse_html_card(card, district, raw_uri)
            if listing:
                listings.append(listing)
    except Exception as exc:
        log.warning("aqar_html_parse_failed", error=str(exc))

    return listings


def _parse_next_data_item(
    item: dict[str, Any], district: dict[str, str], raw_uri: str
) -> dict[str, Any] | None:
    """Parse one listing from Aqar's __NEXT_DATA__ JSON structure."""
    try:
        price = _parse_sar(item.get("price") or item.get("rent"))
        area = _parse_float(item.get("area") or item.get("size"))
        external_id = str(item.get("id") or item.get("referenceNumber") or "")
        if not external_id or not price:
            return None

        return {
            "portal": PORTAL,
            "external_id": external_id,
            "listing_type": "lease",  # warehouse-for-rent endpoint
            "property_type": "warehouse",
            "district": district["name_en"],
            "city": "Riyadh",
            "area_sqm": area,
            "rent_sar_annual": price,
            "url": f"{BASE_URL}/en/{external_id}",
            "raw_json": item,
            "raw_uri": raw_uri,
            "extracted_at": datetime.now(UTC),
            "extractor_version": EXTRACTOR_VERSION,
            "is_active": True,
        }
    except Exception:
        return None


def _parse_html_card(card: Any, district: dict[str, str], raw_uri: str) -> dict[str, Any] | None:
    """Parse one listing card from Aqar HTML (fallback path).

    Aqar's current layout (Next.js App Router, Tailwind):
      <a href="/en/warehouse-for-rent/{city}/{district}/warehouse-for-rent-{id}">
        <div class="flex surface overflow-hidden …">
          <div class="flex-1 …">
            <p>title</p>
            <p class="text-brand font-bold"><span>§165,000</span>/annually</p>
            <ul>…<span>100,275m²</span>…</ul>
          </div>
        </div>
      </a>
    """
    import re as _re

    try:
        # The card element IS the <a> tag
        href = card.attrs.get("href", "")
        if not href:
            return None

        # External ID from URL slug: "warehouse-for-rent-6560504" → "6560504"
        id_match = _re.search(r"warehouse-for-rent-(\d+)$", href)
        external_id = id_match.group(1) if id_match else hashlib.md5(href.encode()).hexdigest()[:16]

        # Price: look for element with class containing "text-brand"
        price_el = card.css_first("[class*='text-brand']")
        if not price_el:
            return None
        price_raw = price_el.text(strip=True)
        # Extract digits only from the part before "/annually"
        price_clean = _re.sub(r"[^\d]", "", price_raw.split("/")[0])
        price = _parse_sar(price_clean)
        if not price:
            return None

        # Area: find span ending with m²
        area: float | None = None
        for span in card.css("span, li"):
            t = span.text(strip=True)
            if "m²" in t:
                area = _parse_float(t.replace("m²", "").replace(",", "").strip())
                break

        # District from URL path when card is on general page
        # e.g. /en/warehouse-for-rent/riyadh/south-of-riyadh/as-sulay/warehouse-for-rent-6560504
        url_district = district["name_en"]  # fallback to the requested district

        return {
            "portal": PORTAL,
            "external_id": external_id,
            "listing_type": "lease",
            "property_type": "warehouse",
            "district": url_district,
            "city": "Riyadh",
            "area_sqm": area,
            "rent_sar_annual": price,
            "url": f"{BASE_URL}{href}" if href.startswith("/") else href,
            "raw_json": {"href": href, "price_raw": price_raw},
            "raw_uri": raw_uri,
            "extracted_at": datetime.now(UTC),
            "extractor_version": EXTRACTOR_VERSION,
            "is_active": True,
        }
    except Exception:
        return None


async def _upsert_listings(session: AsyncSession, listings: list[dict[str, Any]]) -> int:
    count = 0
    for listing in listings:
        stmt = (
            insert(Listing)
            .values(**listing)
            .on_conflict_do_update(
                constraint="uq_listing_portal_external_id",
                set_={
                    "rent_sar_annual": listing.get("rent_sar_annual"),
                    "area_sqm": listing.get("area_sqm"),
                    "is_active": True,
                    "raw_uri": listing["raw_uri"],
                    "extracted_at": listing["extracted_at"],
                    "updated_at": datetime.now(UTC),
                },
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
    """Re-extraction for the outbox reconciler."""
    district_slug = outbox_row.scraper_meta.get("district", "unknown")
    district = next(
        (d for d in TARGET_DISTRICTS if d["slug"] == district_slug),
        {"slug": district_slug, "name_en": district_slug, "name_ar": district_slug},
    )
    listings = _parse_listing_page(raw_bytes.decode(errors="replace"), district, outbox_row.raw_uri)
    await _upsert_listings(session, listings)


# ── Parsing helpers ────────────────────────────────────────────────────────────


def _parse_sar(value: Any) -> float | None:
    """Parse SAR price from various string formats: '1,200,000 SAR', 'ر.س 1200000'."""
    if value is None:
        return None
    cleaned = str(value).replace(",", "").replace("SAR", "").replace("ر.س", "").strip()
    try:
        result = float(cleaned)
        return result if result > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").split()[0]
        return float(cleaned)
    except (ValueError, TypeError, IndexError):
        return None


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


if __name__ == "__main__":
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    # Manual runs use first 3 districts to limit blast radius
    asyncio.run(run_aqar_scraper(districts=_TEST_DISTRICTS))
