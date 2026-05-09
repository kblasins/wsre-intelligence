"""Base scraper class — enforces the raw-first preservation pattern.

Every scraper subclass must call `self.save_raw(content, ext)` before
performing any parsing. This writes the raw blob to the configured BlobStore
(LocalBlobStore in development, S3BlobStore in production) and returns the
storage URI and sha1 hash.

The URI is stored in the raw_ingest_outbox table so the reconciler can
re-download the blob and re-run extraction if the process crashes mid-flight.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import settings
from app.core.storage import upload_raw

log = structlog.get_logger(__name__)

EXTRACTOR_VERSION = "0.1.0"


class ScraperError(Exception):
    """Raised when a scraper fails after all retries."""


class BaseScraper:
    """Abstract base for all data source scrapers."""

    SOURCE: str = ""

    def __init__(self) -> None:
        if not self.SOURCE:
            raise ValueError(f"{self.__class__.__name__} must define SOURCE")
        self._log = log.bind(source=self.SOURCE)

    async def save_raw(
        self,
        content: bytes,
        ext: str,
        *,
        content_type: str = "text/html",
        meta: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Write raw bytes to BlobStore and return (uri, sha1).

        This is always called BEFORE any parsing — the raw blob is the source
        of truth, and the outbox reconciler re-runs extraction from it.
        """
        ts = datetime.now(UTC)
        uri, sha1 = await upload_raw(content, self.SOURCE, ext, content_type=content_type, ts=ts)
        self._log.debug("raw_saved", uri=uri, sha1=sha1[:8], size_bytes=len(content))
        return uri, sha1

    async def _http_get(self, url: str, **kwargs: Any) -> str:
        """Async HTTP GET with retries. Returns response text."""
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
            **kwargs.pop("headers", {}),
        }

        proxy = str(settings.ksa_proxy_url) if settings.ksa_proxy_url else None

        import certifi

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential_jitter(initial=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                    proxy=proxy,
                    verify=certifi.where(),
                ) as client:
                    resp = await client.get(url, **kwargs)
                    resp.raise_for_status()
                    return resp.text

        raise ScraperError(f"All retries exhausted for {url}")
