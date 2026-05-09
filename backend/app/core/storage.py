"""Blob storage abstraction — LocalBlobStore now, S3BlobStore later.

The raw-first preservation pattern requires writing raw bytes to durable
storage BEFORE any structured extraction. The storage implementation is
behind a Protocol so the scrapers don't care whether they're writing to
the local filesystem or an S3-compatible bucket.

Current implementation: LocalBlobStore
  - Writes to ./data/raw/{source}/{YYYY}/{MM}/{DD}/{sha1}.{ext}.gz
  - Same deterministic key convention as the production S3 path
  - No external dependencies, works offline

Future swap: change BLOB_STORE_BACKEND=s3 in .env.local and fill in
S3_* credentials. The swap point is get_blob_store() below.
See README → "Going to production later".

Key convention (identical for both backends):
    {source}/{YYYY}/{MM}/{DD}/{sha1}.{ext}.gz

The sha1 is computed on the uncompressed content — used for dedup and
integrity verification. The file is gzip-compressed before storage.
"""

from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


@runtime_checkable
class BlobStore(Protocol):
    """Interface for raw blob persistence.

    Implementations must be idempotent: putting a blob with the same key
    twice is safe and returns the same key.
    """

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """Write data and return the storage URI (e.g., 'local:///key' or 's3://bucket/key')."""
        ...

    async def get(self, key: str) -> bytes:
        """Read and return decompressed data for the given key."""
        ...

    async def exists(self, key: str) -> bool:
        """Return True if the key already exists in storage."""
        ...


def build_blob_key(source: str, ext: str, sha1: str, ts: datetime | None = None) -> str:
    """Build the deterministic storage key for a raw blob.

    Pattern: {source}/{YYYY}/{MM}/{DD}/{sha1}.{ext}.gz
    The sha1 is of the uncompressed content.
    """
    ts = ts or datetime.now(UTC)
    return str(
        PurePosixPath(source)
        / f"{ts.year:04d}"
        / f"{ts.month:02d}"
        / f"{ts.day:02d}"
        / f"{sha1}.{ext}.gz"
    )


def compute_sha1(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


class LocalBlobStore:
    """Filesystem blob store — writes to settings.blob_store_local_root.

    The directory structure mirrors the S3 key convention exactly, making
    the eventual migration to S3BlobStore a config-only change.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or settings.blob_store_local_root
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)

        compressed = gzip.compress(data, compresslevel=6)
        dest.write_bytes(compressed)

        uri = f"local://{key}"
        log.debug("blob_stored", uri=uri, size_bytes=len(data), compressed_bytes=len(compressed))
        return uri

    async def get(self, key: str) -> bytes:
        path = self._root / key
        if not path.exists():
            raise FileNotFoundError(f"Blob not found: {key}")
        raw = path.read_bytes()
        try:
            return gzip.decompress(raw)
        except gzip.BadGzipFile:
            return raw  # already decompressed (shouldn't happen in normal operation)

    async def exists(self, key: str) -> bool:
        return (self._root / key).exists()


class S3BlobStore:
    """S3-compatible blob store — not yet implemented.

    Fill in S3_* env vars and set BLOB_STORE_BACKEND=s3 to activate.
    See README → "Going to production later".
    """

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        raise NotImplementedError(
            "S3BlobStore is not yet configured. "
            "Set BLOB_STORE_BACKEND=local or configure S3_* credentials."
        )

    async def get(self, key: str) -> bytes:
        raise NotImplementedError("S3BlobStore not configured")

    async def exists(self, key: str) -> bool:
        raise NotImplementedError("S3BlobStore not configured")


_store: BlobStore | None = None


def get_blob_store() -> BlobStore:
    """Return the configured blob store singleton.

    This is the single swap point for the storage backend.
    Change BLOB_STORE_BACKEND in .env.local to switch implementations.
    """
    global _store
    if _store is None:
        _store = S3BlobStore() if settings.blob_store_backend == "s3" else LocalBlobStore()
    return _store


async def upload_raw(
    content: bytes,
    source: str,
    ext: str,
    *,
    content_type: str = "application/octet-stream",
    ts: datetime | None = None,
) -> tuple[str, str]:
    """Convenience wrapper: hash → build key → put blob → return (uri, sha1).

    Used by all scrapers via BaseScraper.save_raw().
    """
    sha1 = compute_sha1(content)
    key = build_blob_key(source, ext, sha1, ts)
    store = get_blob_store()
    uri = await store.put(key, content, content_type=content_type)
    return uri, sha1


async def download_raw(uri: str) -> bytes:
    """Download a blob by its URI. Handles both local:// and s3:// schemes."""
    store = get_blob_store()
    if uri.startswith("local://"):
        key = uri.removeprefix("local://")
    elif uri.startswith("s3://"):
        # Strip bucket prefix for S3BlobStore which manages the bucket internally
        key = "/".join(uri.split("/")[3:])
    else:
        raise ValueError(f"Unknown URI scheme: {uri}")
    return await store.get(key)
