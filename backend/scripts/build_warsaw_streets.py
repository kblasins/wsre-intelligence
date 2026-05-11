"""Build data/warsaw_streets.json by resolving Warsaw streets → districts via Nominatim.

Queries each unique street found in primary_pricing (city=WARSZAWA) against
Nominatim's structured search. Parses the display_name to extract the
Warsaw dzielnica. Saves a normalized street→district JSON for use by
jawnosc_parser.resolve_warsaw_district().

Run once (or when new streets appear):
    python scripts/build_warsaw_streets.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings

log = structlog.get_logger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
OUT_FILE = DATA_DIR / "warsaw_streets.json"

# Canonical district names (Polish, lowercase, no diacritics for key matching)
DISTRICTS_CANONICAL = {
    "srodmiescie":    "śródmieście",
    "srodmiescie poludniowe": "śródmieście",
    "mokotow":        "mokotów",
    "wola":           "wola",
    "praga-poludnie": "praga-południe",
    "praga poludnie": "praga-południe",
    "ursynow":        "ursynów",
    "bialoleka":      "białołęka",
    "bemowo":         "bemowo",
    "bielany":        "bielany",
    "targowek":       "targówek",
    "praga-polnoc":   "praga-północ",
    "praga polnoc":   "praga-północ",
    "ursus":          "ursus",
    "wlochy":         "włochy",
    "wilanow":        "wilanów",
    "ochota":         "ochota",
    "wawer":          "wawer",
    "rembertow":      "rembertów",
    "wesola":         "wesoła",
    "zoliborz":       "żoliborz",
}


def _strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_street_key(street: str) -> str:
    """Lowercase, strip diacritics, strip ul./al./pl. prefix, strip trailing house numbers."""
    s = street.strip()
    # Strip concatenated "Ulica" prefix (e.g. "UlicaBukowiecka")
    s = re.sub(r"^[Uu]lica(?=[A-ZŁŚĄĘĆŻŹŃ])", "", s)
    s = s.lower()
    # Strip street type prefixes
    for prefix in ("ulica ", "ul. ", "ul.", "aleje ", "aleja ", "al. ", "al.",
                   "plac ", "pl. ", "pl.", "błonia ", "bł. ", "bł.", "skwer ",
                   "rondo ", "os. ", "osiedle "):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    # Strip trailing house numbers: " 342", " 25A", " 16, 18 i 18A" etc.
    s = re.sub(r"\s+\d[\d\s,iIaAbBcCdDeEfF/\-]*$", "", s).strip()
    s = _strip_diacritics(s)
    return s


def _extract_district_from_display(display_name: str) -> str | None:
    """Parse Nominatim display_name to find a Warsaw dzielnica."""
    # display_name example:
    # "Geometryczna, Tarchomin, Białołęka, Warszawa, województwo mazowieckie, ..."
    parts = [p.strip() for p in display_name.split(",")]
    for part in parts:
        norm = _strip_diacritics(part.lower())
        if norm in DISTRICTS_CANONICAL:
            return DISTRICTS_CANONICAL[norm]
    # Try substring match
    for key, canonical in DISTRICTS_CANONICAL.items():
        for part in parts:
            if key in _strip_diacritics(part.lower()):
                return canonical
    return None


def _make_async_url(raw: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return raw.replace(prefix, "postgresql+asyncpg://", 1)
    return raw


async def fetch_unique_streets(factory: async_sessionmaker) -> list[str]:
    async with factory() as s:
        r = await s.execute(text("""
            SELECT DISTINCT street
            FROM primary_pricing
            WHERE city = 'WARSZAWA' AND street IS NOT NULL AND street != ''
            ORDER BY street
        """))
        return [row[0] for row in r.fetchall()]


def query_nominatim(street: str, client: httpx.Client) -> str | None:
    """Query Nominatim structured search for a Warsaw street → district."""
    # Normalize first (strip prefix/numbers)
    norm = normalize_street_key(street)
    if not norm:
        return None

    try:
        r = client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "street": norm,
                "city": "Warszawa",
                "country": "Poland",
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
            },
            timeout=10.0,
        )
        r.raise_for_status()
        results = r.json()
    except Exception as exc:
        log.warning("nominatim_error", street=street, error=str(exc))
        return None

    for item in results:
        # Try addressdetails first (most reliable)
        addr = item.get("address", {})
        suburb = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter") or ""
        city_district = addr.get("city_district") or addr.get("district") or ""
        for candidate in [city_district, suburb]:
            if candidate:
                norm_cand = _strip_diacritics(candidate.lower())
                if norm_cand in DISTRICTS_CANONICAL:
                    return DISTRICTS_CANONICAL[norm_cand]

        # Fallback: parse display_name
        display = item.get("display_name", "")
        if "Warszawa" in display:
            district = _extract_district_from_display(display)
            if district:
                return district

    return None


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=1.1,
                        help="Seconds between Nominatim requests (default 1.1)")
    args = parser.parse_args()

    db_url = _make_async_url(str(settings.database_url))
    engine = create_async_engine(db_url, echo=False)
    Factory = async_sessionmaker(engine, expire_on_commit=False)

    streets = await fetch_unique_streets(Factory)
    print(f"Unique Warsaw streets in primary_pricing: {len(streets)}")

    # Load existing map to avoid re-querying
    existing: dict[str, str] = {}
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            existing = json.load(f)
        print(f"Loaded {len(existing)} existing entries from {OUT_FILE.name}")

    result: dict[str, str] = dict(existing)
    resolved = 0
    not_found = []

    with httpx.Client(
        headers={"User-Agent": "WSRE-Intelligence/1.0 (research; contact admin@wsre.local)"},
        follow_redirects=True,
    ) as client:
        for i, street in enumerate(streets, 1):
            key = normalize_street_key(street)
            if not key or key in result:
                continue  # already known

            if args.dry_run:
                print(f"  [{i:3d}] WOULD query: {street!r} → key={key!r}")
                continue

            district = query_nominatim(street, client)
            if district:
                result[key] = district
                resolved += 1
                print(f"  [{i:3d}] {street!r:50s} → {district}")
            else:
                not_found.append(street)
                print(f"  [{i:3d}] {street!r:50s} → NOT FOUND")

            time.sleep(args.delay)  # polite rate limit

    if not args.dry_run:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUT_FILE.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"\nSaved {len(result)} entries to {OUT_FILE}")
        print(f"Resolved this run: {resolved}")
        print(f"Not found ({len(not_found)}): {not_found[:20]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
