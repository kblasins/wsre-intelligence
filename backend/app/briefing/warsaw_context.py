"""Warsaw data context assembler for the weekly brief.

Queries all available Warsaw market data and returns a structured dict that
the Warsaw orchestrator passes to Opus 4.6.

Return contract (mirrors context.py):
  - Text strings without leading underscore  → Opus user-prompt slots
  - Dicts / lists prefixed with _            → PDF template rendering

Data sources (in priority order):
  1. Jawność primary_pricing (live scrape)   — residential price signals
  2. macro_indicators table                  — Polish macro (manually maintained)
  3. news_articles table                     — Polish news sources
  4. plot_regulatory_seed                    — Warsaw regulatory events (curated)
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Warsaw dzielnice canonical list (lowercase, matches primary_pricing.district)
_WARSAW_DZIELNICE_SQL = (
    "'śródmieście','wola','mokotów','ochota','żoliborz','bielany',"
    "'białołęka','targówek','praga-północ','praga-południe',"
    "'rembertów','wesoła','wawer','ursynów','wilanów','włochy','ursus','bemowo'"
)

# Primary market price sanity band (matches plot_evaluation.py)
_PRICE_MIN = 5_000
_PRICE_MAX = 30_000

# Polish news sources active in the ingestion pipeline
_POLISH_SOURCES = (
    "eurobuild_cee",
    "inwestycje_pl",
)

# Macro indicator keys used in the Polish brief
# These live in the macro_indicators table (manually maintained via admin endpoint)
_MACRO_KEYS = (
    "nbp_reference_rate",
    "eur_pln",
    "pln_10y_yield",
    "cpi_yoy",
    "unemployment_rate",
    "pmi_construction",
    "avg_mortgage_rate",
    "gdp_yoy",
    # KPI strip keys
    "warsaw_prime_office_yield",
    "warsaw_office_q1_net_absorption_sqm",
    "warsaw_ytd_investment_volume_meur",
)

# Human labels for macro indicator keys
_MACRO_LABELS: dict[str, str] = {
    "nbp_reference_rate":                  "NBP reference rate (%)",
    "eur_pln":                             "EUR/PLN",
    "pln_10y_yield":                       "Polish 10Y yield (%)",
    "cpi_yoy":                             "CPI YoY (%)",
    "unemployment_rate":                   "Unemployment rate (%)",
    "pmi_construction":                    "PMI Construction",
    "avg_mortgage_rate":                   "Avg mortgage rate (%)",
    "gdp_yoy":                             "GDP YoY (%)",
    "warsaw_prime_office_yield":           "Warsaw prime office yield (%)",
    "warsaw_office_q1_net_absorption_sqm": "Warsaw office Q1 net absorption (sqm)",
    "warsaw_ytd_investment_volume_meur":   "Warsaw YTD investment volume (M EUR)",
}


# ── Developer name cleaning (mirrors plot_evaluation.py) ─────────────────────

_DATASET_TITLE_PREFIXES = (
    "Ceny ofertowe mieszkań i domów dewelopera ",
    "Ceny ofertowe mieszkań dewelopera ",
    "Ceny ofertowe domów dewelopera ",
    "Ceny ofertowe lokali dewelopera ",
)
_DATASET_TITLE_SUFFIX_RE = re.compile(
    r"(\s*-\s*inwestycja\b.*$"
    r"|\s+w\s+\d{4}\s+(i\s+\d{4}\s+)?r\.?\s*$"
    r"|\s+od\s+\d{4}.*$"
    r"|\s+\d{4}\s*r?\.\s*$"
    r"|\s*\.\s*$)",
    re.IGNORECASE,
)


def _clean_dev_name(raw: str) -> str:
    name = raw.strip()
    for prefix in _DATASET_TITLE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return _DATASET_TITLE_SUFFIX_RE.sub("", name).strip() or raw


# ── Guardrail 1: Warsaw geographic filter ─────────────────────────────────────

# Terms that confirm Warsaw or Poland-wide scope → include
_GEO_WARSAW_INCLUDE = frozenset([
    "warsaw", "warszawa",
    # 18 dzielnice (Polish + ASCII fallbacks)
    "śródmieście", "srodmiescie",
    "wola",
    "mokotów", "mokotow",
    "ochota",
    "żoliborz", "zoliborz",
    "bielany",
    "białołęka", "bialoleka",
    "targówek", "targowek",
    "praga-północ", "praga polnoc", "praga północ",
    "praga-południe", "praga poludnie", "praga południe",
    "rembertów", "rembertow",
    "wesoła", "wesola",
    "wawer",
    "ursynów", "ursynow",
    "wilanów", "wilanow",
    "włochy", "wlochy",
    "ursus",
    "bemowo",
    # Poland-wide / national scope
    "poland", "polska", "polish", "national",
    "krajowy", "ogólnopolski", "ogolnopolski",
    "country-wide", "całej polski", "calej polski",
])

# Terms that flag an explicitly non-Warsaw Polish city → exclude if no Warsaw cross-ref
_GEO_NON_WARSAW_CITIES = frozenset([
    "kraków", "krakow",
    "wrocław", "wroclaw",
    "łódź", "lodz",
    "poznań", "poznan",
    "gdańsk", "gdansk",
    "gdynia",
    "katowice",
    "lublin",
    "szczecin",
    "bydgoszcz",
    "toruń", "torun",
    "białystok", "bialystok",
    "rzeszów", "rzeszow",
    "kielce",
    "olsztyn",
    "częstochowa", "czestochowa",
])

# Warsaw-active developers / firms — used for NULL-geography soft-filter
_GEO_WARSAW_DEVELOPERS = frozenset([
    "dom development", "develia", "murapol", "victoria dom", "robyg", "atal",
    "echo investment", "hb reavis", "ghelamco", "skanska", "warimpex",
    "golub", "cornerstone", "dekpol", "yareal", "vastint", "strabag",
    "griffin", "patrizia", "tag immobilien", "vantage development",
    "nuveen", "blackstone", "epp", "ncc", "helical", "crestyl",
    "bouygues", "hochtief", "marvipol", "archicom",
])


def _is_warsaw_relevant_geo(
    geography: str | None,
    *,
    developer: str | None = None,
    entity: str | None = None,
) -> bool:
    """Return True if a fact should appear in the Warsaw brief.

    Guardrail 1 logic:
      - NULL geography → include (liberal; soft-check developer/entity name)
      - Geography contains Warsaw / dzielnica / Poland terms → include
      - Geography contains non-Warsaw Polish city (no Warsaw cross-ref) → exclude
      - Otherwise → include (avoid over-filtering ambiguous data)
    """
    if geography is None:
        # Soft-filter: check if entity/developer is Warsaw-active
        soft = ((developer or "") + " " + (entity or "")).lower()
        for dev in _GEO_WARSAW_DEVELOPERS:
            if dev in soft:
                return True
        return True  # conservative default for NULL geography

    geo = geography.lower()

    for term in _GEO_WARSAW_INCLUDE:
        if term in geo:
            return True

    for city in _GEO_NON_WARSAW_CITIES:
        if city in geo:
            return False  # explicitly non-Warsaw, no cross-ref found

    return True  # ambiguous → include


# ── Main assembler ────────────────────────────────────────────────────────────


async def build_warsaw_context(session: AsyncSession, week_ending: date) -> dict[str, Any]:
    """Assemble all available Warsaw market data for the week ending on `week_ending`.

    Returns a dict with:
      - Formatted text strings for Opus (keys without leading underscore)
      - Structured data for the PDF template (keys prefixed with _)
    """
    week_start = week_ending - timedelta(days=6)

    pricing_text, kpi_strip, price_by_district = await _jawnosc_section(session, week_start, week_ending)
    macro_text, macro_table = await _macro_section(session)
    news_text = await _news_section(session, week_start, week_ending)
    regulatory_text, regulatory_events = await _regulatory_section(session, week_ending)
    facts_text, facts_stats = await _facts_section(session)

    return {
        "week_ending": week_ending.isoformat(),
        "week_start": week_start.isoformat(),
        # Opus-facing formatted text
        "jawnosc_signals": pricing_text,
        "macro": macro_text,
        "news": news_text,
        "regulatory": regulatory_text,
        "facts": facts_text,
        "data_notes": _data_notes(),
        # Template-facing structured data
        "_kpi_strip": kpi_strip,
        "_price_by_district": price_by_district,
        "_macro_table": macro_table,
        "_regulatory_events": regulatory_events,
        "_facts_stats": facts_stats,
        "_week_ending": week_ending.isoformat(),
        "_week_start": week_start.isoformat(),
    }


# ── Jawność / primary pricing section ────────────────────────────────────────


async def _jawnosc_section(
    session: AsyncSession,
    week_start: date,
    week_ending: date,
) -> tuple[str, dict[str, Any], list[dict]]:
    """Returns (opus_text, kpi_strip_dict, price_by_district_list).

    Queries:
      1. Warsaw-wide median + listing count (sanity-filtered)
      2. Median price by district (top 10 by listing count)
      3. Price-change events in the 7-day window (price_history JSONB)
      4. New listings added in the 7-day window (as_of_date)
    """

    # ── 1. Warsaw-wide snapshot ───────────────────────────────────────────────
    snap_r = await session.execute(text(f"""
        SELECT
            COUNT(*)                                          AS total_units,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price)
                                                              AS median_pln_m2,
            COUNT(DISTINCT investment_name)                   AS investment_count,
            MIN(as_of_date)                                   AS oldest_date,
            MAX(as_of_date)                                   AS freshest_date
        FROM primary_pricing
        WHERE status = 'active'
          AND district IN ({_WARSAW_DZIELNICE_SQL})
          AND m2_price > {_PRICE_MIN}
          AND m2_price < {_PRICE_MAX}
    """))
    snap = snap_r.fetchone()

    total_units = int(snap.total_units) if snap and snap.total_units else 0
    median_pln_m2 = round(float(snap.median_pln_m2)) if snap and snap.median_pln_m2 else None
    investment_count = int(snap.investment_count) if snap and snap.investment_count else 0
    freshest_date = snap.freshest_date if snap else None

    # ── 2. Price by district ──────────────────────────────────────────────────
    dist_r = await session.execute(text(f"""
        SELECT
            district,
            COUNT(*)                                          AS unit_count,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price)
                                                              AS median_pln_m2,
            MIN(m2_price)                                     AS min_pln_m2,
            MAX(m2_price)                                     AS max_pln_m2
        FROM primary_pricing
        WHERE status = 'active'
          AND district IN ({_WARSAW_DZIELNICE_SQL})
          AND m2_price > {_PRICE_MIN}
          AND m2_price < {_PRICE_MAX}
        GROUP BY district
        ORDER BY unit_count DESC
        LIMIT 10
    """))
    dist_rows = dist_r.fetchall()

    price_by_district: list[dict] = []
    for r in dist_rows:
        price_by_district.append({
            "district": r.district,
            "unit_count": int(r.unit_count),
            "median_pln_m2": round(float(r.median_pln_m2)) if r.median_pln_m2 else None,
            "min_pln_m2": round(float(r.min_pln_m2)) if r.min_pln_m2 else None,
            "max_pln_m2": round(float(r.max_pln_m2)) if r.max_pln_m2 else None,
        })

    # ── 3. Price-change events in 7-day window ────────────────────────────────
    change_r = await session.execute(text(f"""
        WITH changes AS (
            SELECT
                investment_name,
                district,
                (price_history -> -1 ->> 'date')::date       AS change_date,
                (price_history -> -2 ->> 'm2_price')::numeric AS prev_m2,
                (price_history -> -1 ->> 'm2_price')::numeric AS curr_m2
            FROM primary_pricing
            WHERE status = 'active'
              AND district IN ({_WARSAW_DZIELNICE_SQL})
              AND jsonb_array_length(price_history) >= 2
              AND (price_history -> -1 ->> 'm2_price')::numeric > {_PRICE_MIN}
              AND (price_history -> -1 ->> 'm2_price')::numeric < {_PRICE_MAX}
              AND (price_history -> -2 ->> 'm2_price')::numeric > {_PRICE_MIN}
              AND (price_history -> -1 ->> 'date')::date >= :week_start
              AND (price_history -> -1 ->> 'date')::date <= :week_end
              AND (price_history -> -1 ->> 'm2_price')::numeric
                IS DISTINCT FROM (price_history -> -2 ->> 'm2_price')::numeric
        )
        SELECT
            investment_name,
            district,
            change_date,
            prev_m2,
            curr_m2,
            ROUND(((curr_m2 - prev_m2) / NULLIF(prev_m2, 0)) * 100, 2) AS pct_change
        FROM changes
        WHERE ABS(((curr_m2 - prev_m2) / NULLIF(prev_m2, 0)) * 100) <= 10
        ORDER BY ABS(curr_m2 - prev_m2) DESC
        LIMIT 20
    """), {"week_start": week_start, "week_end": week_ending})
    change_rows = change_r.fetchall()

    # ── 4. New listings in 7-day window ──────────────────────────────────────
    new_r = await session.execute(text(f"""
        SELECT
            COUNT(*)                                          AS new_units,
            COUNT(DISTINCT investment_name)                   AS new_investments,
            COUNT(DISTINCT district)                          AS districts_added
        FROM primary_pricing
        WHERE as_of_date >= :week_start
          AND as_of_date <= :week_end
          AND district IN ({_WARSAW_DZIELNICE_SQL})
          AND m2_price > {_PRICE_MIN}
          AND m2_price < {_PRICE_MAX}
    """), {"week_start": week_start, "week_end": week_ending})
    new_row = new_r.fetchone()
    new_units = int(new_row.new_units) if new_row and new_row.new_units else 0
    new_investments = int(new_row.new_investments) if new_row and new_row.new_investments else 0

    # ── Format KPI strip ──────────────────────────────────────────────────────
    kpi_strip: dict[str, Any] = {
        "avg_primary_pln_m2": median_pln_m2,
        "total_units": total_units,
        "investment_count": investment_count,
        "data_freshness": str(freshest_date) if freshest_date else None,
    }

    # ── Format Opus text ──────────────────────────────────────────────────────
    lines: list[str] = []

    if total_units == 0:
        lines.append(
            "No primary residential pricing data available for Warsaw. "
            "Jawność (dane.gov.pl) scraper has not yet run or returned no results."
        )
        return "\n".join(lines), kpi_strip, price_by_district

    as_of = f" (data as of {freshest_date})" if freshest_date else ""
    lines.append(
        f"WARSAW PRIMARY RESIDENTIAL MARKET{as_of}:\n"
        f"  Active units: {total_units:,} across {investment_count} investments\n"
        f"  Warsaw median: PLN {median_pln_m2:,}/m² (sanity-filtered PLN {_PRICE_MIN:,}–{_PRICE_MAX:,}/m²)"
    )

    if price_by_district:
        lines.append("\nPRICE BY DISTRICT (top 10 by listing volume):")
        for d in price_by_district:
            med = f"PLN {d['median_pln_m2']:,}/m²" if d["median_pln_m2"] else "n/a"
            lines.append(f"  {d['district'].capitalize()}: {d['unit_count']} units · median {med}")

    if new_units > 0:
        lines.append(
            f"\nNEW LISTINGS THIS WEEK: {new_units:,} units across "
            f"{new_investments} investments added to Jawność dataset"
        )
    else:
        lines.append("\nNEW LISTINGS THIS WEEK: No new Jawność entries in the 7-day window.")

    if change_rows:
        lines.append(f"\nPRICE-CHANGE EVENTS THIS WEEK ({len(change_rows)} recorded, ±10% sanity cap):")
        for r in change_rows:
            name = _clean_dev_name(r.investment_name or "unknown investment")
            direction = "▲" if float(r.pct_change or 0) > 0 else "▼"
            pct = f"{float(r.pct_change or 0):+.1f}%"
            prev = f"PLN {float(r.prev_m2):,.0f}"
            curr = f"PLN {float(r.curr_m2):,.0f}"
            lines.append(
                f"  {r.change_date} | {r.district} | {name}: "
                f"{prev} → {curr} {direction}{pct}"
            )
    else:
        lines.append(
            "\nPRICE-CHANGE EVENTS THIS WEEK: "
            "No Jawność price changes recorded in the 7-day window."
        )

    return "\n".join(lines), kpi_strip, price_by_district


# ── Macro section ─────────────────────────────────────────────────────────────


async def _macro_section(session: AsyncSession) -> tuple[str, list[dict]]:
    """Pull Polish macro indicators from macro_indicators table.

    Returns (opus_text, macro_table_rows).
    """
    keys_sql = ", ".join(f"'{k}'" for k in _MACRO_KEYS)
    r = await session.execute(text(f"""
        SELECT indicator_key, value, period, source, fetched_at
        FROM macro_indicators
        WHERE indicator_key IN ({keys_sql})
        ORDER BY indicator_key
    """))
    rows = r.fetchall()

    if not rows:
        return (
            "No Polish macro indicators available. "
            "Populate via POST /api/admin/macro-indicators/{{key}} for keys: "
            + ", ".join(_MACRO_KEYS[:8]),
            [],
        )

    # Build structured table (exclude KPI-strip-only keys from main macro table)
    _KPI_ONLY = {
        "warsaw_prime_office_yield",
        "warsaw_office_q1_net_absorption_sqm",
        "warsaw_ytd_investment_volume_meur",
    }

    macro_table: list[dict] = []
    lines = ["POLISH MACRO INDICATORS:"]

    for row in rows:
        label = _MACRO_LABELS.get(row.indicator_key, row.indicator_key)
        val = float(row.value)
        fetched = row.fetched_at.strftime("%-d %b %Y") if row.fetched_at else "date unknown"

        entry = {
            "key": row.indicator_key,
            "label": label,
            "value": val,
            "period": row.period,
            "source": row.source,
            "fetched_at": str(row.fetched_at.date()) if row.fetched_at else None,
        }

        if row.indicator_key not in _KPI_ONLY:
            macro_table.append(entry)
            lines.append(f"  {label}: {val} | period={row.period} | source={row.source} [{fetched}]")

    available_keys = {row.indicator_key for row in rows}
    missing = [k for k in _MACRO_KEYS[:8] if k not in available_keys]
    if missing:
        lines.append(
            f"\n  Data gaps: {', '.join(missing)} not yet populated in macro_indicators table."
        )

    return "\n".join(lines), macro_table


# ── News section ──────────────────────────────────────────────────────────────


async def _news_section(
    session: AsyncSession,
    week_start: date,
    week_ending: date,
) -> str:
    """Return Polish news articles from the week.

    Filters: Polish sources, relevance >= 0.5, within the 7-day window.
    Falls back to most recent if nothing in the window.
    """
    week_start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=UTC)
    week_end_dt = datetime.combine(week_ending, datetime.max.time()).replace(tzinfo=UTC)

    sources_sql = ", ".join(f"'{s}'" for s in _POLISH_SOURCES)

    r = await session.execute(text(f"""
        SELECT source, title_en, title_ar, url, published_at, relevance_score
        FROM news_articles
        WHERE published_at >= :s
          AND published_at <= :e
          AND relevance_score >= 0.5
          AND source IN ({sources_sql})
        ORDER BY relevance_score DESC
        LIMIT 20
    """), {"s": week_start_dt, "e": week_end_dt})
    articles = r.fetchall()

    if not articles:
        # Try most recent Polish news regardless of date
        r2 = await session.execute(text(f"""
            SELECT source, title_en, title_ar, url, published_at, relevance_score
            FROM news_articles
            WHERE relevance_score >= 0.5
              AND source IN ({sources_sql})
            ORDER BY relevance_score DESC
            LIMIT 10
        """))
        articles = r2.fetchall()
        if not articles:
            return (
                "No Polish news data available. "
                "Polish news sources (Rzeczpospolita, Wyborcza Biznes, JLL PL research, etc.) "
                "are not yet configured in the news scraper pipeline. "
                "This section will be populated once Polish-language news ingestion is active."
            )

    lines = [f"POLISH NEWS ({len(articles)} articles, relevance ≥ 0.5):"]
    for a in articles:
        title = a.title_en or a.title_ar or "(no title)"
        score = f"{float(a.relevance_score):.2f}" if a.relevance_score is not None else "?"
        pub = a.published_at.strftime("%-d %b %Y") if a.published_at else "date unknown"
        lines.append(f"\n  [{score}] [{pub}] [{a.source}] {title}")
    return "\n".join(lines)


# ── Regulatory section ────────────────────────────────────────────────────────


async def _regulatory_section(
    session: AsyncSession,
    week_ending: date,
) -> tuple[str, list[dict]]:
    """Pull Warsaw regulatory events.

    Sources (in order):
      1. plot_regulatory_seed — curated demo events (last 180 days)
      2. regulatory_events table — if any Polish events exist
    """
    cutoff = week_ending - timedelta(days=180)
    events: list[dict] = []

    # ── Source 1: plot_regulatory_seed ────────────────────────────────────────
    # Table-level events (not plot-specific; using event_date to filter)
    seed_r = await session.execute(text("""
        SELECT event_date, title, source, link_url
        FROM plot_regulatory_seed
        WHERE event_date >= :cutoff
        ORDER BY event_date DESC
        LIMIT 10
    """), {"cutoff": cutoff})
    seed_rows = seed_r.fetchall()

    for r in seed_rows:
        events.append({
            "event_date": str(r.event_date),
            "title": r.title,
            "source": r.source,
            "link_url": r.link_url,
            "table": "plot_regulatory_seed",
        })

    # ── Source 2: regulatory_events table ────────────────────────────────────
    reg_r = await session.execute(text("""
        SELECT event_type, authority, scope, effective_date, summary, source_citation
        FROM regulatory_events
        WHERE created_at >= :cutoff
          AND (
            authority ILIKE '%warszawa%'
            OR authority ILIKE '%poland%'
            OR authority ILIKE '%polska%'
            OR authority ILIKE '%NBP%'
            OR authority ILIKE '%UKNF%'
            OR authority ILIKE '%GUS%'
          )
        ORDER BY created_at DESC
        LIMIT 10
    """), {"cutoff": datetime.combine(cutoff, datetime.min.time()).replace(tzinfo=UTC)})
    reg_rows = reg_r.fetchall()

    for r in reg_rows:
        events.append({
            "event_date": str(r.effective_date) if r.effective_date else None,
            "title": r.summary or "(no summary)",
            "source": r.authority or "unknown",
            "link_url": None,
            "table": "regulatory_events",
        })

    if not events:
        return (
            "No Warsaw regulatory events in the last 180 days. "
            "Populate plot_regulatory_seed or regulatory_events with Polish RE news.",
            [],
        )

    lines = [f"WARSAW REGULATORY EVENTS ({len(events)} records, last 180 days):"]
    for e in events:
        date_str = e["event_date"] or "date unknown"
        link = f" [{e['link_url']}]" if e.get("link_url") else ""
        lines.append(f"  {date_str} | {e['source']}: {e['title']}{link}")

    return "\n".join(lines), events


# ── Guardrail 1: Facts section with Warsaw geographic filter ──────────────────

_FACTS_SOURCES_SQL = "('eurobuild_cee', 'inwestycje_pl')"


async def _facts_section(
    session: AsyncSession,
) -> tuple[str, dict[str, dict[str, int]]]:
    """Pull geo-filtered facts from all 8 typed tables for Polish sources.

    Applies Guardrail 1: only Warsaw / dzielnice / Poland-wide facts pass.
    Tables without a geography field (capital_markets, macro, market_commentary)
    are included in full — they are already Polish-sourced and Poland-wide relevant.

    Returns (opus_formatted_text, stats).
    stats = {table_name: {"total": N, "warsaw": M}}
    """
    S = _FACTS_SOURCES_SQL
    stats: dict[str, dict[str, int]] = {}
    blocks: list[str] = []

    # ── Supply events ─────────────────────────────────────────────────────────
    r = await session.execute(text(f"""
        SELECT se.event_type, se.developer, se.project_name,
               se.location_description, se.district_guess,
               se.asset_class, se.gfa_sqm, se.confidence, se.source_citation,
               a.title_en, a.published_at
        FROM supply_events se
        JOIN news_articles a ON a.id = se.article_id
        WHERE a.source IN {S} AND se.confidence >= 4
        ORDER BY se.confidence DESC, a.published_at DESC NULLS LAST
    """))
    all_rows = r.fetchall()
    filtered = [
        row for row in all_rows
        if _is_warsaw_relevant_geo(
            " ".join(filter(None, [row.location_description, row.district_guess])) or None,
            developer=row.developer,
        )
    ]
    stats["supply_events"] = {"total": len(all_rows), "warsaw": len(filtered)}
    if filtered:
        lines = [f"SUPPLY EVENTS ({len(filtered)} Warsaw-relevant of {len(all_rows)} total):"]
        for row in filtered[:25]:
            parts = [row.event_type or "event"]
            if row.developer:
                parts.append(f"developer={row.developer}")
            if row.project_name:
                parts.append(f"project={row.project_name}")
            loc = " / ".join(filter(None, [row.district_guess, row.location_description]))
            if loc:
                parts.append(f"location={loc}")
            if row.asset_class:
                parts.append(f"class={row.asset_class}")
            if row.gfa_sqm:
                parts.append(f"gfa={row.gfa_sqm}sqm")
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {' · '.join(parts)}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Capital markets events ────────────────────────────────────────────────
    # No geography field — include all Polish-sourced facts
    r = await session.execute(text(f"""
        SELECT cme.event_type, cme.entity, cme.ticker_if_listed,
               cme.value_sar, cme.confidence, cme.source_citation,
               a.title_en, a.published_at
        FROM capital_markets_events cme
        JOIN news_articles a ON a.id = cme.article_id
        WHERE a.source IN {S} AND cme.confidence >= 4
        ORDER BY cme.confidence DESC, a.published_at DESC NULLS LAST
    """))
    cm_rows = r.fetchall()
    stats["capital_markets_events"] = {"total": len(cm_rows), "warsaw": len(cm_rows)}
    if cm_rows:
        lines = [f"CAPITAL MARKETS EVENTS ({len(cm_rows)} facts):"]
        for row in cm_rows[:20]:
            parts = [row.event_type or "event"]
            if row.entity:
                parts.append(f"entity={row.entity}")
            if row.value_sar:
                parts.append(f"value={row.value_sar}")
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {' · '.join(parts)}\n"
                f"    Article: {(row.title_en or '(no title)')[:80]}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Macro signals ─────────────────────────────────────────────────────────
    # No geography field — Polish macro is inherently Poland-wide relevant
    r = await session.execute(text(f"""
        SELECT ms.indicator, ms.period, ms.value, ms.direction,
               ms.magnitude, ms.confidence, ms.source_citation,
               a.title_en, a.published_at
        FROM macro_signals ms
        JOIN news_articles a ON a.id = ms.article_id
        WHERE a.source IN {S} AND ms.confidence >= 4
        ORDER BY ms.confidence DESC, a.published_at DESC NULLS LAST
    """))
    macro_rows = r.fetchall()
    stats["macro_signals"] = {"total": len(macro_rows), "warsaw": len(macro_rows)}
    if macro_rows:
        _DIR = {"up": "↑", "down": "↓", "flat": "→"}
        lines = [f"MACRO SIGNALS ({len(macro_rows)} facts):"]
        for row in macro_rows[:20]:
            d = _DIR.get(row.direction or "", "?")
            parts = [f"{row.indicator} {d}", f"period={row.period or '?'}"]
            if row.value:
                parts.append(f"value={row.value}")
            if row.magnitude:
                parts.append(f"magnitude={row.magnitude}")
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {' · '.join(parts)}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Demand signals ────────────────────────────────────────────────────────
    r = await session.execute(text(f"""
        SELECT ds.sector, ds.metric, ds.value, ds.period,
               ds.geography, ds.confidence, ds.source_citation,
               a.title_en, a.published_at
        FROM demand_signals ds
        JOIN news_articles a ON a.id = ds.article_id
        WHERE a.source IN {S} AND ds.confidence >= 4
        ORDER BY ds.confidence DESC, a.published_at DESC NULLS LAST
    """))
    all_rows = r.fetchall()
    filtered = [row for row in all_rows if _is_warsaw_relevant_geo(row.geography)]
    stats["demand_signals"] = {"total": len(all_rows), "warsaw": len(filtered)}
    if filtered:
        lines = [f"DEMAND SIGNALS ({len(filtered)} Warsaw-relevant of {len(all_rows)} total):"]
        for row in filtered[:25]:
            parts = [
                f"sector={row.sector or '?'}",
                f"metric={row.metric or '?'}",
                f"value={row.value or '?'}",
                f"period={row.period or '?'}",
            ]
            if row.geography:
                parts.append(f"geo={row.geography}")
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {' · '.join(parts)}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Tenant signals ────────────────────────────────────────────────────────
    r = await session.execute(text(f"""
        SELECT ts.tenant_name, ts.industry, ts.event_type,
               ts.geography, ts.confidence, ts.source_citation,
               a.title_en, a.published_at
        FROM tenant_signals ts
        JOIN news_articles a ON a.id = ts.article_id
        WHERE a.source IN {S} AND ts.confidence >= 4
        ORDER BY ts.confidence DESC, a.published_at DESC NULLS LAST
    """))
    all_rows = r.fetchall()
    filtered = [row for row in all_rows if _is_warsaw_relevant_geo(row.geography)]
    stats["tenant_signals"] = {"total": len(all_rows), "warsaw": len(filtered)}
    if filtered:
        lines = [f"TENANT SIGNALS ({len(filtered)} Warsaw-relevant of {len(all_rows)} total):"]
        for row in filtered:
            geo_str = f" · geo={row.geography}" if row.geography else ""
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {row.tenant_name or '?'} ({row.industry or '?'})"
                f" · {row.event_type or '?'}{geo_str}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Regulatory events ─────────────────────────────────────────────────────
    r = await session.execute(text(f"""
        SELECT re.event_type, re.authority, re.scope,
               re.effective_date, re.summary,
               re.confidence, re.source_citation,
               a.title_en, a.published_at
        FROM regulatory_events re
        JOIN news_articles a ON a.id = re.article_id
        WHERE a.source IN {S} AND re.confidence >= 4
        ORDER BY re.confidence DESC, a.published_at DESC NULLS LAST
    """))
    all_rows = r.fetchall()
    # Filter: include Warsaw/Polish authorities; exclude foreign authority mentions
    filtered = [
        row for row in all_rows
        if _is_warsaw_relevant_geo(row.authority or None)
    ]
    stats["regulatory_events"] = {"total": len(all_rows), "warsaw": len(filtered)}
    if filtered:
        lines = [f"REGULATORY EVENTS ({len(filtered)} facts):"]
        for row in filtered:
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {row.event_type or '?'}"
                f" · authority={row.authority or '?'} · scope={row.scope or '?'}\n"
                f"    Summary: {(row.summary or '(none)')[:120]}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Market commentary ─────────────────────────────────────────────────────
    # No geography — include all (already Polish-sourced; cap at 20)
    r = await session.execute(text(f"""
        SELECT mc.source_authority, mc.topic, mc.quote_under_15_words,
               mc.confidence, mc.source_citation,
               a.title_en, a.published_at
        FROM market_commentary mc
        JOIN news_articles a ON a.id = mc.article_id
        WHERE a.source IN {S} AND mc.confidence >= 4
        ORDER BY mc.confidence DESC, a.published_at DESC NULLS LAST
        LIMIT 20
    """))
    mc_rows = r.fetchall()
    stats["market_commentary"] = {"total": len(mc_rows), "warsaw": len(mc_rows)}
    if mc_rows:
        lines = [f"MARKET COMMENTARY ({len(mc_rows)} quotes, top 20):"]
        for row in mc_rows:
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] [{row.source_authority or 'unknown'}]"
                f" topic={row.topic or '?'}\n"
                f"    Quote: \"{row.quote_under_15_words or '(none)'}\"\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Infrastructure events ─────────────────────────────────────────────────
    r = await session.execute(text(f"""
        SELECT ie.project, ie.infra_type, ie.phase,
               ie.location, ie.completion_date,
               ie.confidence, ie.source_citation,
               a.title_en, a.published_at
        FROM infrastructure_events ie
        JOIN news_articles a ON a.id = ie.article_id
        WHERE a.source IN {S} AND ie.confidence >= 4
        ORDER BY ie.confidence DESC, a.published_at DESC NULLS LAST
    """))
    all_rows = r.fetchall()
    filtered = [row for row in all_rows if _is_warsaw_relevant_geo(row.location)]
    stats["infrastructure_events"] = {"total": len(all_rows), "warsaw": len(filtered)}
    if filtered:
        lines = [f"INFRASTRUCTURE EVENTS ({len(filtered)} Warsaw-relevant of {len(all_rows)} total):"]
        for row in filtered:
            pub = row.published_at.strftime("%-d %b %Y") if row.published_at else "?"
            lines.append(
                f"  [{row.confidence}★] {row.project or '?'} · type={row.infra_type or '?'}"
                f" · phase={row.phase or '?'} · location={row.location or '?'}\n"
                f"    Citation: \"{row.source_citation}\" [{pub}]"
            )
        blocks.append("\n".join(lines))

    # ── Summary header ────────────────────────────────────────────────────────
    total_all = sum(v["total"] for v in stats.values())
    total_warsaw = sum(v["warsaw"] for v in stats.values())
    header = (
        f"EXTRACTED FACTS — WARSAW GEO-FILTERED "
        f"({total_warsaw} facts surviving filter of {total_all} total across 8 tables):"
    )
    if not blocks:
        return header + "\n  No facts found with confidence ≥ 4 in any table.", stats

    return header + "\n\n" + "\n\n".join(blocks), stats


# ── Data notes ────────────────────────────────────────────────────────────────


def _data_notes() -> str:
    return (
        "Data quality notes (Warsaw brief):\n"
        "- Jawność primary_pricing: official dane.gov.pl developer disclosure; "
        "sanity filter PLN 5,000–30,000/m² applied; scraper may not have run this week\n"
        "- Macro indicators: manually maintained via admin endpoint; "
        "may be stale if not refreshed this week\n"
        "- News sources active: eurobuild_cee (RSS, English-language CEE trade press) "
        "and inwestycje_pl (Polish financial news); last 30 days ingested\n"
        "- Extracted facts: 8 typed tables from 46 articles (confidence ≥ 4 threshold); "
        "Warsaw geo-filter applied\n"
        "- Transaction data (notarial deeds / GUS): not available — no direct data feed\n"
        "- Office leasing data: no JLL/CBRE/Colliers PL research PDFs parsed; "
        "inferred from news articles only\n"
        "- Broader Polish RE press (Rzeczpospolita, Wyborcza Biznes, Puls Biznesu): "
        "not yet in scraper pipeline\n"
        "- Acknowledge all gaps explicitly — institutional readers expect honesty"
    )
