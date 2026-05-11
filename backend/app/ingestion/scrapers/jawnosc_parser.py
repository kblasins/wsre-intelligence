"""Jawnosc cen mieszkan — multi-format pricing file parser.

Handles three data formats published by Polish developers under Dz.U. 2023 poz. 1114:

  1. CSV  — standard MRiT recommended format (~60 columns, semicolon-delimited)
  2. XLSX — same MRiT schema in Excel workbook (openpyxl)
  3. JSON — wyslijdane.pl API format (nested: investments→buildings→properties)

All three parsers return a list of ParsedDwelling dataclasses with a
common normalized interface ready for upsert into primary_pricing.

Schema variants documented (hand-tested against 20 Warsaw feeds, 2026-05-09):
  MRT-v1   Standard MRiT CSV; "Nr lokalu lub domu jednorodzinnego nadany przez dewelopera"
           for unit ID; long Polish column names; semicolon delimiter.
  MRT-v2   Marvipol/Develia XLSX: shorter column labels ("Nr lokalu nadany przez dewelopera");
           price fields use Polish decimal comma ("21000,00" → 21000.0).
  MRT-v3   Dom Development XLSX: same MRiT but voivodeship column uses "mazowieckie" lowercase.
  MRT-v4   Some CSV feeds: comma delimiter (rare); BOM absent.
  JSON-WD  wyslijdane.pl: {investments: [{city, buildings: [{properties: [{number,
           price, area, pricePerMeter, isSold, additionalFees}]}]}]}.
           Has explicit area and isSold; no price_date.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import structlog

try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

log = structlog.get_logger(__name__)

# ── Status normalisation ───────────────────────────────────────────────────────

STATUS_MAP: dict[str, str] = {
    # Polish
    "aktywne": "active",
    "aktywny": "active",
    "wolne": "active",
    "wolny": "active",
    "dostępne": "active",
    "w sprzedaży": "active",
    "zarezerwowane": "reserved",
    "rezerwacja": "reserved",
    "sprzedane": "sold",
    "sprzedany": "sold",
    "wycofane": "withdrawn",
    "wycofany": "withdrawn",
    "niedostępne": "withdrawn",
    # English
    "active": "active",
    "available": "active",
    "free": "active",
    "reserved": "reserved",
    "sold": "sold",
    "withdrawn": "withdrawn",
    "unavailable": "withdrawn",
    # English from wyslijdane.pl isSold=True
    "issold_true": "sold",
    "issold_false": "active",
}


def normalize_status(raw: Any) -> str:
    if isinstance(raw, bool):
        return "sold" if raw else "active"
    if raw is None or str(raw).strip() in ("", "x", "X", "-"):
        return "active"  # assumed active if not marked otherwise
    return STATUS_MAP.get(str(raw).strip().lower(), "active")


# ── Price / number helpers ─────────────────────────────────────────────────────

def _parse_pl_decimal(val: Any) -> float | None:
    """Parse Polish decimal: '21 000,00' or '21000,00' or '21000.00' → 21000.0."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "x", "X", "-", "0"):
        return None
    # Remove spaces (thousand separators)
    s = s.replace(" ", "").replace("\xa0", "")
    # Polish comma decimal → dot
    s = s.replace(",", ".")
    # Remove any remaining non-numeric except dot and minus
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    s = str(val).strip()
    if not s or s in ("x", "X", "-"):
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


# ── Normalized dwelling dataclass ──────────────────────────────────────────────

@dataclass
class ParsedDwelling:
    """Normalized dwelling unit ready for primary_pricing upsert."""
    dwelling_id: str
    investment_name: str
    district: str | None
    city: str
    street: str | None
    voivodeship: str | None
    m2_price: float | None
    total_price: float | None
    unit_area: float | None
    unit_type: str | None
    status: str                     # active | reserved | sold | withdrawn
    price_date: date | None
    source_format: str              # csv | xlsx | json
    schema_variant: str             # MRT-v1 | MRT-v2 | JSON-WD | etc.
    raw_unit_id: str | None = None  # unmodified developer unit ID


# ── Column-header matching helpers ────────────────────────────────────────────

def _col_idx(headers: list[str], *synonyms: str) -> int | None:
    h = [h.lower().strip() for h in headers]
    for syn in synonyms:
        syn_l = syn.lower().strip()
        for i, hh in enumerate(h):
            if syn_l in hh:
                return i
    return None


# ── MRiT flat-row parser (shared by CSV and XLSX) ─────────────────────────────

# Standard positional indices (MRiT recommended, 0-indexed after header row)
_MRT_VOIV_INV = 28    # Województwo lokalizacji przedsięwzięcia
_MRT_CITY_INV = 31    # Miejscowość lokalizacji
_MRT_STREET_INV = 32  # Ulica lokalizacji
_MRT_TYPE = 35        # Rodzaj nieruchomości
_MRT_UNIT_ID = 36     # Nr lokalu lub domu
_MRT_M2_PRICE = 37    # Cena m2
_MRT_M2_DATE = 38     # Data od której cena m2 obowiązuje
_MRT_TOTAL_PRICE = 39 # Cena całkowita (iloczyn m2 × powierzchnia)
_MRT_FULL_PRICE = 41  # Cena uwzględniająca inne składowe (preferred over col 39)


def _detect_mrt_variant(headers: list[str]) -> str:
    """Detect MRT schema variant from headers."""
    h_concat = " ".join(h.lower() for h in headers[:10])
    if "lokalizacja przedsięwzięcia" in h_concat or "lokalizacja ... - woj" in h_concat:
        return "MRT-v2"
    if "nr lokalu lub domu" in " ".join(h.lower() for h in headers):
        return "MRT-v1"
    return "MRT-v1"


def _parse_mrt_rows(
    headers: list[str],
    data_rows: list[list[Any]],
    source_format: str,
) -> list[ParsedDwelling]:
    """Parse a list of MRiT-format rows (CSV or XLSX) into ParsedDwelling list."""
    variant = _detect_mrt_variant(headers)

    # Dynamic column detection (override positional if header found)
    city_col = _col_idx(headers,
        "miejscowość lokalizacji",
        "miejscowosc lokalizacji",
        "lokalizacja przedsięwzięcia deweloperskiego lub zadania inwestycyjnego - miejscowość",
    ) or _MRT_CITY_INV

    voiv_col = _col_idx(headers,
        "województwo lokalizacji",
        "lokalizacja przedsięwzięcia deweloperskiego lub zadania inwestycyjnego - województwo",
    ) or _MRT_VOIV_INV

    street_col = _col_idx(headers,
        "ulica lokalizacji",
        "lokalizacja przedsięwzięcia deweloperskiego lub zadania inwestycyjnego - ulica",
    ) or _MRT_STREET_INV

    type_col = _col_idx(headers,
        "rodzaj nieruchomości",
        "rodzaj nieruchomosci",
    ) or _MRT_TYPE

    unit_id_col = _col_idx(headers,
        "nr lokalu lub domu jednorodzinnego nadany",
        "nr lokalu nadany",
        "numer lokalu",
        "nr_lokalu",
    ) or _MRT_UNIT_ID

    m2_price_col = _col_idx(headers,
        "cena m 2 powierzchni użytkowej",
        "cena m2 powierzchni",
        "cena_m2",
        "cena m2",
    ) or _MRT_M2_PRICE

    m2_date_col = _col_idx(headers,
        "data od której cena obowiązuje cena m 2",
        "data od której cena m 2",
        "data_cena_m2",
    ) or _MRT_M2_DATE

    # Prefer full price (col 41) over base price (col 39)
    full_price_col = _col_idx(headers,
        "uwzględniająca cenę lokalu stanowiącą iloczyn powierzchni oraz metrażu i innych składowych",
        "uwzgledniajaca cene lokalu i innych skladowych",
        "cena lokalu mieszkalnego lub domu jednorodzinnego uwzględniająca",
    )
    total_price_col = _col_idx(headers,
        "cena lokalu mieszkalnego lub domu jednorodzinnego będących przedmiotem umowy stanowiąca iloczyn ceny m2 oraz powierzchni",
        "cena lokalu...stanowiąca iloczyn",
        "cena_total",
    ) or _MRT_TOTAL_PRICE

    # Investment name: try to derive from developer name + city
    dev_name_col = 0  # Column 0 is always "Nazwa dewelopera"

    results: list[ParsedDwelling] = []

    for row in data_rows:
        def cell(idx: int) -> Any:
            return row[idx] if idx < len(row) else None

        city_raw = str(cell(city_col) or "").strip()
        voiv_raw = str(cell(voiv_col) or "").strip()
        street_raw = str(cell(street_col) or "").strip()
        unit_id_raw = str(cell(unit_id_col) or "").strip()
        m2_price = _parse_pl_decimal(cell(m2_price_col))
        # Prefer full price (includes extra fees) but fall back to base total price
        # when the full price column is absent or null (most rows don't carry extra fees).
        total_price = (
            (_parse_pl_decimal(cell(full_price_col)) if full_price_col is not None else None)
            or _parse_pl_decimal(cell(total_price_col))
        )
        price_date = _parse_date(cell(m2_date_col))
        unit_type = str(cell(type_col) or "").strip() or None
        dev_name = str(cell(dev_name_col) or "").strip()

        # Skip empty rows
        if not unit_id_raw or unit_id_raw in ("x", "X", "-"):
            continue

        # Derive area from total_price / m2_price
        unit_area: float | None = None
        if total_price and m2_price and m2_price > 0:
            unit_area = round(total_price / m2_price, 2)

        # Status: not present in MRiT format; units in the file are active
        # (sold/withdrawn units disappear from the next day's file)
        status = "active"

        # Investment name: developer name is the proxy for the investment
        # (each jawnosc_developers row = one investment)
        investment_name = dev_name or "unknown"

        # Dwelling ID: unique per (investment, unit)
        dwelling_id = unit_id_raw

        results.append(ParsedDwelling(
            dwelling_id=dwelling_id,
            investment_name=investment_name,
            district=None,  # resolved in ingestion job from city/street
            city=city_raw.upper() if city_raw else "UNKNOWN",
            street=street_raw or None,
            voivodeship=voiv_raw.lower() or None,
            m2_price=m2_price,
            total_price=total_price,
            unit_area=unit_area,
            unit_type=unit_type,
            status=status,
            price_date=price_date,
            source_format=source_format,
            schema_variant=variant,
            raw_unit_id=unit_id_raw,
        ))

    return results


# ── CSV parser ─────────────────────────────────────────────────────────────────

class CsvParser:
    """Parse MRiT-format CSV. Handles BOM, semicolon/comma delimiter, UTF-8 variants."""

    @staticmethod
    def parse(content: bytes) -> tuple[list[ParsedDwelling], str | None]:
        """Returns (dwellings, error_message_or_None)."""
        try:
            text = content.decode("utf-8-sig", errors="replace")
        except Exception as exc:
            return [], f"decode_error: {exc}"

        # Auto-detect delimiter
        sample = text[:4000]
        delim = ";" if sample.count(";") >= sample.count(",") else ","

        try:
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            rows = list(reader)
        except Exception as exc:
            return [], f"csv_parse_error: {exc}"

        if not rows:
            return [], "empty_file"

        headers = rows[0]
        data_rows = rows[1:]

        # Sanity: at least 25 columns expected (some short-schema feeds use ~30)
        if len(headers) < 25:
            return [], f"too_few_columns: {len(headers)}"

        # Validate it looks like MRiT data
        h_concat = " ".join(h.lower() for h in headers[:5])
        if "nazwa" not in h_concat and "dewelopera" not in h_concat:
            return [], "schema_unrecognized"

        dwellings = _parse_mrt_rows(headers, data_rows, "csv")
        return dwellings, None


# ── XLSX parser ───────────────────────────────────────────────────────────────

class XlsxParser:
    """Parse MRiT-format XLSX (openpyxl). Handles multiple sheets."""

    @staticmethod
    def parse(content: bytes) -> tuple[list[ParsedDwelling], str | None]:
        if not _HAS_OPENPYXL:
            return [], "openpyxl_not_installed"
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            return [], f"xlsx_open_error: {exc}"

        ws = wb.active
        try:
            all_rows = list(ws.iter_rows(values_only=True))
        except Exception as exc:
            return [], f"xlsx_read_error: {exc}"

        if not all_rows:
            return [], "empty_sheet"

        headers = [str(h) if h is not None else "" for h in all_rows[0]]
        data_rows = [list(row) for row in all_rows[1:]]

        if len(headers) < 25:
            return [], f"too_few_columns: {len(headers)}"

        dwellings = _parse_mrt_rows(headers, data_rows, "xlsx")
        return dwellings, None


# ── JSON (wyslijdane.pl) parser ───────────────────────────────────────────────

class JsonWdParser:
    """Parse wyslijdane.pl JSON format.

    Structure:
        {
          "dataSetName": ...,
          "developer": {...},
          "offerDate": "2026-05-10",
          "investments": [{
            "investmentName": ...,
            "city": ...,
            "street": ...,
            "voivodeship": ...,
            "buildings": [{
              "properties": [{
                "number": "A026",
                "price": 771330.0,
                "area": 36.73,
                "pricePerMeter": 21000.0,
                "isSold": false,
                "additionalFees": [...]
              }]
            }]
          }]
        }
    """

    @staticmethod
    def parse(content: bytes) -> tuple[list[ParsedDwelling], str | None]:
        try:
            text = content.decode("utf-8-sig", errors="replace")
            data = json.loads(text)
        except Exception as exc:
            return [], f"json_parse_error: {exc}"

        if not isinstance(data, dict):
            return [], "json_not_object"

        investments = data.get("investments") or []
        if not investments:
            # Some feeds have a flat properties list directly
            if "properties" in data:
                investments = [{"investmentName": data.get("dataSetName", ""), "properties_flat": data["properties"]}]
            else:
                return [], "no_investments_key"

        offer_date_raw = data.get("offerDate")
        offer_date = _parse_date(offer_date_raw)

        results: list[ParsedDwelling] = []

        for inv in investments:
            inv_name = inv.get("investmentName") or inv.get("name") or ""
            inv_city = (inv.get("city") or "").strip().upper()
            inv_street = inv.get("street") or None
            inv_voiv = (inv.get("voivodeship") or "").strip().lower()

            # Handle flat properties list (non-standard)
            if "properties_flat" in inv:
                buildings = [{"properties": inv["properties_flat"]}]
            else:
                buildings = inv.get("buildings") or []

            for building in buildings:
                props = building.get("properties") or []
                for prop in props:
                    unit_num = str(prop.get("number") or prop.get("id") or "").strip()
                    if not unit_num:
                        continue

                    price = _parse_pl_decimal(prop.get("price") or prop.get("totalPrice"))
                    area = _parse_pl_decimal(prop.get("area") or prop.get("m2"))
                    price_m2 = _parse_pl_decimal(prop.get("pricePerMeter") or prop.get("priceM2"))

                    # Derive missing m2_price or area
                    if price and area and not price_m2 and area > 0:
                        price_m2 = round(price / area, 2)
                    if price and price_m2 and not area and price_m2 > 0:
                        area = round(price / price_m2, 2)

                    # Status
                    is_sold = prop.get("isSold")
                    status_raw = prop.get("status")
                    if is_sold is not None:
                        status = "sold" if is_sold else "active"
                    elif status_raw:
                        status = normalize_status(status_raw)
                    else:
                        status = "active"

                    results.append(ParsedDwelling(
                        dwelling_id=unit_num,
                        investment_name=inv_name,
                        district=None,
                        city=inv_city,
                        street=inv_street,
                        voivodeship=inv_voiv or None,
                        m2_price=price_m2,
                        total_price=price,
                        unit_area=area,
                        unit_type=str(prop.get("type") or "").strip() or None,
                        status=status,
                        price_date=offer_date,
                        source_format="json",
                        schema_variant="JSON-WD",
                        raw_unit_id=unit_num,
                    ))

        return results, None


# ── Dispatcher ────────────────────────────────────────────────────────────────

def parse_feed_file(
    content: bytes,
    fmt: str,
) -> tuple[list[ParsedDwelling], str | None]:
    """Dispatch to the right parser based on file extension/format.

    Returns (dwellings, error_or_None).
    """
    fmt = (fmt or "").lower()
    if fmt in ("csv",):
        return CsvParser.parse(content)
    elif fmt in ("xlsx", "xls"):
        return XlsxParser.parse(content)
    elif fmt in ("json",):
        return JsonWdParser.parse(content)
    else:
        # Try CSV first as the most common
        dwellings, err = CsvParser.parse(content)
        if dwellings:
            return dwellings, None
        # Try XLSX
        if _HAS_OPENPYXL:
            dwellings, err = XlsxParser.parse(content)
            if dwellings:
                return dwellings, None
        # Try JSON
        dwellings, err = JsonWdParser.parse(content)
        return dwellings, err


# ── Warsaw district resolver ──────────────────────────────────────────────────

_WARSAW_STREETS_FILE = Path(__file__).parent.parent.parent.parent.parent / "data" / "warsaw_streets.json"
_STREET_MAP: dict[str, str] | None = None

# Postal-code prefix → district fallback (first 2 digits of Polish 5-digit code)
_POSTAL_DISTRICT: dict[str, str] = {
    "00": "śródmieście",
    "01": "wola",
    "02": "mokotów",
    "03": "praga-południe",
    "04": "mokotów",
    "05": "wawer",       # outer ring — best effort
    "06": "praga-północ",
    "07": "białołęka",
    "08": "targówek",
}

_STREET_PREFIX_RE = re.compile(
    r"^(ulica|ul\.?\s*|aleje\s+|aleja\s+|al\.?\s*|plac\s+|pl\.?\s*|błonia\s+|bł\.?\s*|skwer\s+|rondo\s+|os\.\s*|osiedle\s+)",
    re.IGNORECASE,
)
_TRAILING_NUMBER_RE = re.compile(r"\s+\d[\d\s,i/aAbBcCdDeEfF\-]*$")
_ULICA_CONCAT_RE = re.compile(r"^[Uu]lica(?=[A-ZŁŚĄĘĆŻŹŃ])")


def _normalize_street_key(street: str) -> str:
    """Lowercase, no diacritics, strip ul./al./pl. prefix, strip trailing house numbers."""
    s = _ULICA_CONCAT_RE.sub("", street.strip())
    s = _STREET_PREFIX_RE.sub("", s).strip()
    s = _TRAILING_NUMBER_RE.sub("", s).strip()
    s = s.lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return s


def _load_street_map() -> dict[str, str]:
    global _STREET_MAP
    if _STREET_MAP is None:
        if _WARSAW_STREETS_FILE.exists():
            with _WARSAW_STREETS_FILE.open(encoding="utf-8") as f:
                raw = json.load(f)
            # Strip meta keys
            _STREET_MAP = {k: v for k, v in raw.items() if not k.startswith("_")}
        else:
            _STREET_MAP = {}
    return _STREET_MAP


def resolve_warsaw_district(
    city: str,
    street: str | None,
    voivodeship: str | None,
    postal_code: str | None = None,
) -> str | None:
    """Resolve Warsaw district from city + street (+ postal code fallback).

    Resolution order:
      1. Exact normalized-street match in warsaw_streets.json
      2. Substring scan of the comprehensive street map (handles compound names)
      3. Postal code prefix → district (coarse fallback)
    """
    if not city or "WARSZAWA" not in city.upper():
        return None

    street_map = _load_street_map()

    if street:
        key = _normalize_street_key(street)
        # 1. Exact match
        if key in street_map:
            return street_map[key]
        # 2. Substring scan — handles "ul. Marszałka Piłsudskiego" → key contains "piłsudskiego"
        for fragment, district in street_map.items():
            if len(fragment) >= 5 and fragment in key:
                return district

    # 3. Postal code fallback
    if postal_code:
        prefix = postal_code.replace("-", "").strip()[:2]
        if prefix in _POSTAL_DISTRICT:
            return _POSTAL_DISTRICT[prefix]

    return None
