"""Jawnosc cen mieszkan — dane.gov.pl ingestion module.

Legal basis: Dz.U. 2023 poz. 1114 (art. 19b ustawy z dnia 20 maja 2021 r.
o ochronie praw nabywcy lokalu mieszkalnego lub domu jednorodzinnego
oraz Deweloperskim Funduszu Gwarancyjnym).

Every primary-market developer must publish daily, machine-readable files
containing every apartment price, every price change, every reservation.
These are filed to dane.gov.pl by the Ministry of Digitisation (MRiT).
License: CC0.

Architecture:
  DaneGovClient     — CKAN API connector (paginated, rate-limited)
  JawNoscDiscovery  — discovers and populates jawnosc_developers registry
  FeedCatalogParser — parses the developer XML catalog → extracts latest data URL
  PricingFileParser — parses a single daily CSV/XLSX pricing snapshot

Discovery strategy (Sub-phase 2A):
  1. Page ALL datasets with tag 'Deweloper' from the CKAN API (~16k nationally)
  2. For each dataset, extract dataset_id, developer_name, source.url (XML catalog),
     institution_id, institution city (HQ address)
  3. For Warsaw-active detection: sample the latest data file and check if
     'Miejscowość lokalizacji' contains a Warsaw district / 'Warszawa'
  4. Upsert into jawnosc_developers with Warsaw flag

Warsaw detection hierarchy (applied in order, stops at first match):
  a) Title contains known Warsaw investment keyword (street/district name)
  b) Institution.city == 'Warszawa' (HQ address — developer likely Warsaw-focused)
  c) Sample latest data file → parse location columns
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import structlog

log = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DANE_GOV_API = "https://api.dane.gov.pl/1.4"
USER_AGENT = (
    "WSRE-Intelligence/1.0 (Warsaw real-estate analytics; "
    "contact: admin@wsre.local; "
    "legal basis: CC0 open data dane.gov.pl)"
)

# 18 Warsaw dzielnice (administrative districts)
WARSAW_DISTRICTS = {
    "śródmieście", "mokotów", "wola", "praga-południe", "ursynów",
    "białołęka", "bemowo", "bielany", "targówek", "praga-północ",
    "ursus", "włochy", "wilanów", "ochota", "wawer", "rembertów",
    "wesoła", "żoliborz",
}

# Aliases and common spellings
WARSAW_DISTRICT_ALIASES = {
    "praga południe": "praga-południe",
    "praga polnoc": "praga-północ",
    "praga północ": "praga-północ",
    "zoliborz": "żoliborz",
    "bialoleka": "białołęka",
}

# Warsaw streets / landmarks that unambiguously identify Warsaw investments
# (used for title-based heuristic)
WARSAW_TITLE_SIGNALS = re.compile(
    r"\b(warszawa|wola|mokotów|żoliborz|ursynów|wilanów|śródmieście"
    r"|białołęka|bemowo|bielany|targówek|ursus|włochy|ochota|wawer"
    r"|praga.?południe|praga.?północ|rembertów|wesoła"
    r"|jerozolimskie|marszałkowska|puławska|woronicza|służewiec"
    r"|kabaty|natolin|natoliński|królikarnia|sielce|czerniakowska"
    r"|marymont|żerań|bródno|gocław|grochów|saska kępa"
    r"|praga|nowa praga|stara praga)\b",
    re.IGNORECASE,
)

# Columns in the MRiT-recommended Jawnosc CSV schema (0-indexed positions)
# Actual column headers are long Polish strings; these are positional fallbacks.
COL_VOIVODESHIP_INVESTMENT = 28   # Województwo lokalizacji przedsięwzięcia
COL_GMINA_INVESTMENT = 30         # Gmina lokalizacji (gmina = municipality)
COL_CITY_INVESTMENT = 31          # Miejscowość lokalizacji
COL_STREET_INVESTMENT = 32        # Ulica lokalizacji
COL_UNIT_ID = 36                  # Nr lokalu lub domu nadany przez dewelopera
COL_M2_PRICE = 37                 # Cena m2 [zł]
COL_PRICE_DATE = 38               # Data od której cena m2 obowiązuje
COL_TOTAL_PRICE = 39              # Cena całkowita [zł]

# Column header substrings to recognize dynamically (schema variation handling)
HEADER_SYNONYMS_CITY = [
    "miejscowość lokalizacji",
    "miejscowosci lokalizacji",
    "miasto lokalizacji",
    "miejscowosc inwestycji",
]
HEADER_SYNONYMS_VOIVODESHIP = [
    "województwo lokalizacji",
    "wojewodztwo lokalizacji",
    "woj. lokalizacji",
]


# ── HTTP client ────────────────────────────────────────────────────────────────

class DaneGovClient:
    """Polite CKAN API client with rate-limiting and retries."""

    def __init__(
        self,
        *,
        requests_per_second: float = 3.0,
        timeout: float = 30.0,
        max_retries: int = 4,
    ) -> None:
        self._rps = requests_per_second
        self._min_interval = 1.0 / requests_per_second
        self._last_request: float = 0.0
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "DaneGovClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def get_json(self, url: str, **params: Any) -> dict[str, Any]:
        await self._throttle()
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, httpx.TransportError) as exc:
                if attempt == self._max_retries - 1:
                    raise
                wait = 2 ** attempt
                log.warning("dane_gov_retry", attempt=attempt + 1, wait=wait, error=str(exc))
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")

    async def get_bytes(self, url: str) -> bytes:
        """Fetch a raw file (CSV / XLSX / XML) with retries."""
        await self._throttle()
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                return resp.content
            except (httpx.HTTPError, httpx.TransportError) as exc:
                if attempt == self._max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("unreachable")

    async def paginate_datasets(
        self,
        query: str = "deweloper",
        per_page: int = 100,
        modified_after: datetime | None = None,
        max_pages: int | None = None,
    ):
        """Async generator yielding raw dataset attribute dicts."""
        page = 1
        params: dict[str, Any] = {
            "q": query,
            "per_page": per_page,
            "sort": "-modified",
        }
        if modified_after:
            params["modified_after"] = modified_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        while True:
            params["page"] = page
            data = await self.get_json(f"{DANE_GOV_API}/datasets", **params)
            items = data.get("data", [])
            if not items:
                break

            for item in items:
                yield item

            total = data.get("meta", {}).get("count", 0)
            if page * per_page >= total:
                break
            if max_pages and page >= max_pages:
                break
            page += 1

    async def get_institution(self, institution_id: str, slug: str) -> dict[str, Any]:
        url = f"{DANE_GOV_API}/institutions/{institution_id},{slug}"
        data = await self.get_json(url)
        return data.get("data", {}).get("attributes", {})


# ── Feed catalog parser ────────────────────────────────────────────────────────

class FeedCatalogParser:
    """Parses the developer XML catalog to find the latest daily data file URL."""

    @staticmethod
    def parse(xml_bytes: bytes) -> dict[str, Any]:
        """Return {latest_url, schema_version, data_format, resource_count}."""
        result: dict[str, Any] = {
            "latest_url": None,
            "schema_version": None,
            "data_format": None,
            "resource_count": 0,
        }
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            log.warning("feed_catalog_parse_error", error=str(exc))
            return result

        # Detect schema version from namespace
        ns_match = re.search(r"urn:otwarte-dane:harvester:([0-9.]+)", xml_bytes.decode("utf-8", errors="replace"))
        if ns_match:
            result["schema_version"] = ns_match.group(1)

        # Strip namespace for simpler XPath
        ns = {"ns": re.search(r"\{(.+?)\}", root.tag).group(1)} if root.tag.startswith("{") else {}

        def find_all(node: ET.Element, tag: str) -> list[ET.Element]:
            if ns:
                return node.findall(f"ns:{tag}", ns) or node.findall(tag)
            return node.findall(tag)

        def find_text(node: ET.Element, tag: str) -> str | None:
            el = node.find(f"ns:{tag}", ns) if ns else node.find(tag)
            return el.text.strip() if el is not None and el.text else None

        # Collect all resource URLs
        resources = []
        for dataset_el in root.iter():
            if dataset_el.tag.endswith("dataset") or dataset_el.tag == "dataset":
                for res_el in dataset_el.iter():
                    if res_el.tag.endswith("resource") or res_el.tag == "resource":
                        url_el = None
                        for child in res_el:
                            if child.tag.endswith("url") or child.tag == "url":
                                url_el = child
                                break
                        date_el = None
                        for child in res_el:
                            if "dataDate" in child.tag or "data_date" in child.tag:
                                date_el = child
                                break
                        if url_el is not None and url_el.text:
                            resources.append({
                                "url": url_el.text.strip(),
                                "date": date_el.text.strip() if date_el is not None and date_el.text else "",
                            })

        result["resource_count"] = len(resources)

        if resources:
            # Sort by date descending, pick the most recent
            resources.sort(key=lambda r: r["date"], reverse=True)
            latest = resources[0]["url"]
            result["latest_url"] = latest
            # Detect format
            ext = latest.rsplit(".", 1)[-1].lower()
            result["data_format"] = ext if ext in ("csv", "xlsx", "xls", "json") else "csv"

        return result


# ── Pricing file parser ────────────────────────────────────────────────────────

class PricingFileParser:
    """Parses a single daily Jawnosc pricing CSV snapshot.

    Handles the main schema variants:
    - Standard MRiT CSV (semicolon or comma separated, UTF-8 BOM)
    - Non-standard column ordering (detected via header matching)
    - Missing optional columns
    """

    REQUIRED_HEADERS = [
        "cena m",        # m2 price fragment
        "miejscowość",   # city
    ]

    @staticmethod
    def _detect_delimiter(sample: str) -> str:
        semicolons = sample.count(";")
        commas = sample.count(",")
        return ";" if semicolons > commas else ","

    @staticmethod
    def _find_col(headers: list[str], synonyms: list[str]) -> int | None:
        h_lower = [h.lower().strip() for h in headers]
        for i, h in enumerate(h_lower):
            for syn in synonyms:
                if syn in h:
                    return i
        return None

    @classmethod
    def parse_csv(cls, raw: bytes) -> dict[str, Any]:
        """Parse CSV bytes. Returns {is_warsaw, districts, unit_count, schema_ok}."""
        result: dict[str, Any] = {
            "is_warsaw": False,
            "districts": [],
            "city": None,
            "voivodeship": None,
            "unit_count": 0,
            "schema_ok": False,
            "error": None,
        }
        try:
            # Handle BOM
            text = raw.decode("utf-8-sig", errors="replace")
        except Exception as exc:
            result["error"] = f"decode_error: {exc}"
            return result

        sample = text[:2000]
        delim = cls._detect_delimiter(sample)

        try:
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            rows = list(reader)
        except Exception as exc:
            result["error"] = f"csv_parse_error: {exc}"
            return result

        if not rows:
            result["error"] = "empty_file"
            return result

        headers = rows[0]
        data_rows = rows[1:]

        # Validate minimum schema
        h_concat = " ".join(h.lower() for h in headers)
        if not any(kw in h_concat for kw in ["cena", "miejscowość", "lokal", "nr lok"]):
            result["error"] = "schema_unrecognized"
            return result

        result["schema_ok"] = True

        # Find key columns
        city_col = cls._find_col(headers, HEADER_SYNONYMS_CITY)
        voiv_col = cls._find_col(headers, HEADER_SYNONYMS_VOIVODESHIP)

        # Fallback to positional
        if city_col is None and len(headers) > COL_CITY_INVESTMENT:
            city_col = COL_CITY_INVESTMENT
        if voiv_col is None and len(headers) > COL_VOIVODESHIP_INVESTMENT:
            voiv_col = COL_VOIVODESHIP_INVESTMENT

        cities_seen: set[str] = set()
        result["unit_count"] = len(data_rows)

        for row in data_rows:
            if city_col is not None and city_col < len(row):
                city = row[city_col].strip().upper()
                cities_seen.add(city)
                if "WARSZAWA" in city:
                    result["is_warsaw"] = True
                    result["city"] = "Warszawa"

        if cities_seen:
            result["city"] = ", ".join(sorted(cities_seen)[:3])

        return result

    @classmethod
    def detect_districts_from_csv(cls, raw: bytes) -> list[str]:
        """Extract Warsaw district names from street/address data."""
        text = raw.decode("utf-8-sig", errors="replace")
        districts_found: set[str] = set()
        text_lower = text.lower()
        for district in WARSAW_DISTRICTS:
            if district in text_lower:
                districts_found.add(district)
        return sorted(districts_found)


# ── Discovery orchestrator ─────────────────────────────────────────────────────

class JawNoscDiscovery:
    """Orchestrates discovery of all Jawnosc developer datasets.

    Sub-phase 2A: builds jawnosc_developers registry.
    """

    def __init__(
        self,
        client: DaneGovClient,
        *,
        sample_for_warsaw: bool = True,
        active_cutoff_days: int = 30,
        max_pages: int | None = None,
    ) -> None:
        self._client = client
        self._sample = sample_for_warsaw
        self._cutoff = timedelta(days=active_cutoff_days)
        self._max_pages = max_pages

    def _is_title_warsaw(self, title: str) -> bool:
        return bool(WARSAW_TITLE_SIGNALS.search(title))

    def _is_recently_active(self, modified_str: str) -> bool:
        if not modified_str:
            return False
        try:
            dt = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
            return datetime.now(UTC) - dt <= self._cutoff
        except ValueError:
            return False

    async def _get_institution_city(
        self, inst_rel: dict[str, Any]
    ) -> str | None:
        """Fetch institution data to get HQ city."""
        try:
            inst_data = inst_rel.get("data", {})
            inst_id = inst_data.get("id", "")
            inst_link = inst_rel.get("links", {}).get("related", "")
            slug = inst_link.split(",")[-1].rstrip("/") if "," in inst_link else ""
            if not inst_id or not slug:
                return None
            attrs = await self._client.get_institution(inst_id, slug)
            return (attrs.get("city") or "").strip() or None
        except Exception:
            return None

    async def _probe_feed(
        self, feed_url: str, *, force_sample: bool = False
    ) -> dict[str, Any]:
        """Fetch the XML catalog and sample the latest daily file."""
        result: dict[str, Any] = {
            "latest_url": None,
            "schema_version": None,
            "data_format": None,
            "is_warsaw": False,
            "districts": [],
            "unit_count": 0,
            "schema_ok": False,
            "error": None,
        }

        # 1. Fetch XML catalog
        try:
            xml_bytes = await self._client.get_bytes(feed_url)
        except Exception as exc:
            result["error"] = f"feed_unreachable: {exc}"
            return result

        catalog = FeedCatalogParser.parse(xml_bytes)
        result.update({
            "latest_url": catalog["latest_url"],
            "schema_version": catalog["schema_version"],
            "data_format": catalog["data_format"],
        })

        if not catalog["latest_url"]:
            result["error"] = "no_resources_in_catalog"
            return result

        # 2. Sample the latest daily file (CSV only; skip XLSX for now)
        if not (self._sample or force_sample):
            return result

        data_url = catalog["latest_url"]
        fmt = catalog.get("data_format", "csv")

        if fmt not in ("csv",):
            # For XLSX, skip sampling in 2A — mark for schema detection in 2B
            result["data_format"] = fmt
            return result

        try:
            raw = await self._client.get_bytes(data_url)
        except Exception as exc:
            result["error"] = f"data_file_unreachable: {exc}"
            return result

        parse_result = PricingFileParser.parse_csv(raw)
        result["is_warsaw"] = parse_result["is_warsaw"]
        result["districts"] = PricingFileParser.detect_districts_from_csv(raw)
        result["unit_count"] = parse_result["unit_count"]
        result["schema_ok"] = parse_result["schema_ok"]
        if parse_result.get("error"):
            result["error"] = parse_result["error"]

        return result

    async def discover(
        self,
        *,
        warsaw_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Page through ALL developer datasets and build the registry.

        Returns a list of developer dicts ready for upsert into jawnosc_developers.
        """
        records: list[dict[str, Any]] = []
        total_seen = 0
        warsaw_count = 0
        stale_count = 0
        error_count = 0

        log.info("jawnosc_discovery_start", max_pages=self._max_pages)

        async for item in self._client.paginate_datasets(
            query="deweloper",
            per_page=100,
            max_pages=self._max_pages,
        ):
            total_seen += 1
            attrs = item.get("attributes", {})
            title_raw = attrs.get("title", "") or ""
            # Strip HTML mark tags from title
            title = re.sub(r"<[^>]+>", "", title_raw).strip()
            dataset_id = str(item.get("id", ""))
            modified_str = attrs.get("modified", "") or ""
            source = attrs.get("source") or {}
            feed_url = source.get("url") or None
            institution_rel = item.get("relationships", {}).get("institution", {})
            inst_data = institution_rel.get("data", {})
            institution_id = inst_data.get("id", "") or ""

            # Dataset URL
            dataset_url = item.get("links", {}).get("self", "")

            # Activity filter
            is_active = self._is_recently_active(modified_str)
            if not is_active:
                stale_count += 1

            # Warsaw tier-1: title heuristic (fast, no HTTP)
            title_warsaw = self._is_title_warsaw(title)

            record: dict[str, Any] = {
                "developer_name": title,
                "developer_id": dataset_id,
                "institution_id": institution_id,
                "dataset_url": dataset_url,
                "feed_url": feed_url,
                "schema_version": None,
                "last_sync": None,
                "sync_status": "active" if is_active else "stale",
                "coverage_districts": [],
                "active_investments_count": 0,
                "active_units_count": 0,
                "city_hq": None,
                "dataset_modified": modified_str or None,
                "data_format": None,
                "is_warsaw_candidate": title_warsaw,
            }

            records.append(record)

            if total_seen % 500 == 0:
                log.info(
                    "jawnosc_discovery_progress",
                    seen=total_seen,
                    warsaw_candidate=warsaw_count,
                    stale=stale_count,
                )

        log.info(
            "jawnosc_discovery_complete",
            total=total_seen,
            stale=stale_count,
            errors=error_count,
        )
        return records

    async def probe_warsaw_candidates(
        self,
        records: list[dict[str, Any]],
        *,
        max_probe: int = 300,
    ) -> list[dict[str, Any]]:
        """For Warsaw candidates that have a feed_url, probe the live feed.

        Updates records in place; returns the updated list.
        """
        candidates = [
            r for r in records
            if r.get("feed_url") and r.get("is_warsaw_candidate")
        ][:max_probe]

        log.info("jawnosc_probe_start", candidates=len(candidates))

        for i, record in enumerate(candidates):
            try:
                probe = await self._probe_feed(record["feed_url"])
                record["schema_version"] = probe.get("schema_version")
                record["data_format"] = probe.get("data_format")
                record["coverage_districts"] = probe.get("districts", [])
                record["active_units_count"] = probe.get("unit_count", 0)

                if probe.get("is_warsaw"):
                    record["sync_status"] = "active"
                elif probe.get("error"):
                    if "unreachable" in (probe["error"] or ""):
                        record["sync_status"] = "unreachable"
                    elif "schema" in (probe["error"] or ""):
                        record["sync_status"] = "schema_error"

                if i % 20 == 0:
                    log.info("jawnosc_probe_progress", done=i + 1, total=len(candidates))
            except Exception as exc:
                log.warning("jawnosc_probe_exception", developer_id=record["developer_id"], error=str(exc))
                record["sync_status"] = "unreachable"

        return records

    async def probe_active_feeds_parallel(
        self,
        records: list[dict[str, Any]],
        *,
        max_probe: int = 2000,
        concurrency: int = 15,
    ) -> list[dict[str, Any]]:
        """Parallel-probe all active feeds to detect Warsaw investments.

        Faster than sequential probing: ~200 concurrent × 2s = <2 min for 1600 feeds.
        """
        active = [
            r for r in records
            if r.get("sync_status") == "active" and r.get("feed_url")
        ][:max_probe]

        log.info("jawnosc_parallel_probe_start", feeds=len(active), concurrency=concurrency)

        sem = asyncio.Semaphore(concurrency)
        done_count = 0

        async def probe_one(record: dict[str, Any]) -> None:
            nonlocal done_count
            async with sem:
                try:
                    probe = await self._probe_feed(record["feed_url"], force_sample=True)
                    record["schema_version"] = probe.get("schema_version")
                    record["data_format"] = probe.get("data_format")
                    record["coverage_districts"] = probe.get("districts", [])
                    record["active_units_count"] = probe.get("unit_count", 0)

                    if probe.get("is_warsaw"):
                        record["is_warsaw_candidate"] = True
                    if probe.get("error") and "unreachable" in (probe["error"] or ""):
                        record["sync_status"] = "unreachable"
                    elif probe.get("error") and "schema" in (probe["error"] or ""):
                        record["sync_status"] = "schema_error"
                except Exception as exc:
                    log.debug("probe_error", developer_id=record["developer_id"], error=str(exc))
                    record["sync_status"] = "unreachable"

                done_count += 1
                if done_count % 50 == 0:
                    log.info("jawnosc_parallel_probe_progress", done=done_count, total=len(active))

        await asyncio.gather(*[probe_one(r) for r in active])
        return records


# ── Standalone discovery runner (used by scripts/discover_jawnosc.py) ──────────

async def run_discovery(
    *,
    max_pages: int | None = None,
    probe: bool = True,
    max_probe: int = 200,
    parallel_probe: bool = False,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Full discovery run. Returns summary statistics + records."""
    async with DaneGovClient(requests_per_second=3.0) as client:
        discovery = JawNoscDiscovery(
            client,
            sample_for_warsaw=probe and not parallel_probe,
            max_pages=max_pages,
        )
        records = await discovery.discover()

        if probe:
            if parallel_probe:
                records = await discovery.probe_active_feeds_parallel(
                    records, max_probe=max_probe, concurrency=15
                )
            else:
                records = await discovery.probe_warsaw_candidates(
                    records, max_probe=max_probe
                )

    # Compute summary statistics
    total = len(records)
    stale = sum(1 for r in records if r["sync_status"] == "stale")
    active = sum(1 for r in records if r["sync_status"] == "active")
    unreachable = sum(1 for r in records if r["sync_status"] == "unreachable")
    schema_error = sum(1 for r in records if r["sync_status"] == "schema_error")
    warsaw_candidates = sum(1 for r in records if r.get("is_warsaw_candidate"))
    warsaw_confirmed = sum(1 for r in records if r.get("is_warsaw_candidate") and r.get("active_units_count", 0) > 0)

    return {
        "records": records,
        "stats": {
            "total_discovered": total,
            "active": active,
            "stale": stale,
            "unreachable": unreachable,
            "schema_error": schema_error,
            "warsaw_candidates_by_title": warsaw_candidates,
            "warsaw_confirmed_by_data": warsaw_confirmed,
        },
    }
