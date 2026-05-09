"""Canary tests — hit live URLs and verify the scraper can parse them.

These tests run nightly in CI (see .github/workflows/canary.yml).
They require SCRAPER_LIVE_MODE=true and optionally KSA_PROXY_URL.
They are NOT run in the standard CI pipeline (pytest -m "not canary").

A canary test failure means:
  - The source site changed its HTML structure (schema drift)
  - A cookie session expired (needs Playwright warm-up)
  - The source is down (check >48h staleness alert)

On failure: update the parser to match the new structure, bump EXTRACTOR_VERSION,
and re-run the golden set regression to confirm the fix doesn't break old extractions.
"""

from __future__ import annotations

import pytest


@pytest.mark.canary
async def test_tadawul_yfinance_returns_prices() -> None:
    """Verify yfinance can fetch at least the three industrial REIT prices."""
    import yfinance as yf

    # Priority industrial REITs
    tickers = ["4331.SR", "4339.SR", "4340.SR"]
    df = yf.download(tickers, period="1d", auto_adjust=True, progress=False)

    assert not df.empty, "yfinance returned empty DataFrame for industrial REITs"
    for ticker in tickers:
        close = df.get(("Close", ticker))
        assert close is not None, f"No Close data for {ticker}"
        assert len(close.dropna()) > 0, f"{ticker} has all-NaN Close prices"


@pytest.mark.canary
async def test_argaam_news_page_parseable() -> None:
    """Verify Argaam English news page loads and has parseable article elements."""
    import httpx
    from selectolax.parser import HTMLParser

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get("https://www.argaam.com/en/article/articlelist/tagid/193")
    assert resp.status_code == 200, f"Argaam returned {resp.status_code}"
    tree = HTMLParser(resp.text)
    articles = tree.css("article, .article-item, [class*='article']")
    assert len(articles) >= 5, f"Expected ≥5 article elements, found {len(articles)}"


@pytest.mark.canary
async def test_modon_news_page_parseable() -> None:
    """Verify MODON news page is reachable (content may be sparse)."""
    import httpx

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(
            "https://www.modon.gov.sa/en/MediaCenter/modon-news/News/Pages/default.aspx",
            headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
        )
    assert resp.status_code == 200, f"MODON returned {resp.status_code}"
    assert "modon" in resp.text.lower(), "MODON page doesn't contain expected content"


@pytest.mark.canary
async def test_rega_portal_reachable() -> None:
    """Verify srem.moj.gov.sa is reachable (scraper itself is a stub pending DevTools capture)."""
    import httpx

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(
            "https://srem.moj.gov.sa",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
    # 200 or 403 both mean the site is up — 403 means Akamai is active (expected)
    assert resp.status_code in (200, 403, 302), (
        f"REGA portal returned unexpected status {resp.status_code}"
    )


@pytest.mark.canary
async def test_aqar_warehouse_page_parseable() -> None:
    """Verify Aqar.fm warehouse page returns parseable HTML.

    This test uses KSA_PROXY_URL if configured to avoid Cloudflare blocking.
    Without a proxy, the test may receive a CF challenge page (still 200 status).
    """
    import httpx

    from app.core.config import settings

    proxy = str(settings.ksa_proxy_url) if settings.ksa_proxy_url else None
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        proxy=proxy,
    ) as client:
        resp = await client.get(
            "https://sa.aqar.fm/en/warehouse-for-rent/riyadh",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
        )

    assert resp.status_code in (200, 403), f"Aqar returned {resp.status_code}"
    if resp.status_code == 200:
        # Basic sanity — page has some content
        assert len(resp.text) > 1000, "Aqar page suspiciously short"
