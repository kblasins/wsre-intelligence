"""Data context assembler for the weekly brief.

Queries all available market data and returns a structured dict that the
orchestrator passes to Opus 4.6. Returns:
  - Pre-formatted text strings (for Opus input prompt)
  - Structured dicts prefixed with "_" (stored in brief_json for template rendering)

Typed fact tables (macro_signals, regulatory_events, etc.) are included in
full — all rows within the 7-day window — so Opus has the complete picture.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text

from app.models.market import Listing, NewsArticle, ReitSnapshot, RentIndex, Tender, Transaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Industrial REITs — always featured prominently in the brief
INDUSTRIAL_TICKERS = {"4331.SR", "4339.SR", "4340.SR"}

# Active news sources only (dropped sources excluded from brief context)
_ACTIVE_SOURCES = ("argaam_en", "argaam_ar", "logistics_me")

# Geography tokens that signal non-KSA content
_NON_KSA_TOKENS = (
    "Dubai", "UAE", "Abu Dhabi", "Sharjah", "Doha", "Qatar",
    "Muscat", "Oman", "Kuwait", "Bahrain", "Egypt", "Jordan",
    "Istanbul", "Turkey", "Iran", "Iraq", "Lebanon",
)


async def build_brief_context(session: AsyncSession, week_ending: date) -> dict:
    """Assemble all available data for the week ending on `week_ending`.

    Returns a dict with:
      - Formatted text strings for Opus (keys without leading underscore)
      - Structured data for the PDF template (keys prefixed with _)
    """
    week_start = week_ending - timedelta(days=6)

    reit_rows, reit_text = await _reit_section(session)
    listing_stats, listing_text = await _listing_section(session)
    facts_text, facts_structured = await _typed_facts_section(session, week_start, week_ending)

    return {
        "week_ending": week_ending.isoformat(),
        "week_start": week_start.isoformat(),
        # Opus-facing formatted text
        "reits": reit_text,
        "transactions": await _transaction_section(session, week_start, week_ending),
        "listings": listing_text,
        "rent_index": await _rent_index_section(session),
        "news": await _news_section(session, week_start, week_ending),
        "facts": facts_text,
        "tenders": await _tender_section(session, week_start, week_ending),
        "data_notes": _data_notes(),
        # Template-facing structured data
        "_reit_rows": reit_rows,
        "_listing_stats": listing_stats,
        "_facts_structured": facts_structured,
    }


# ── REIT section ────────────────────────────────────────────────────────────


async def _reit_section(session: AsyncSession) -> tuple[list[dict], str]:
    """Latest snapshot per ticker + WoW delta via LAG window over snapshot_date.

    Returns (structured_rows, formatted_text) for template and Opus respectively.
    """
    rows = await session.execute(text("""
        WITH latest AS (
            SELECT ticker, MAX(snapshot_date) AS max_date
            FROM reit_snapshots
            GROUP BY ticker
        ),
        prev_week AS (
            SELECT r.ticker, r.price_sar AS prev_price, r.snapshot_date AS prev_date
            FROM reit_snapshots r
            JOIN (
                SELECT ticker, MAX(snapshot_date) AS prev_max
                FROM reit_snapshots
                WHERE snapshot_date < (SELECT MAX(snapshot_date) FROM reit_snapshots) - INTERVAL '5 days'
                GROUP BY ticker
            ) pw ON r.ticker = pw.ticker AND r.snapshot_date = pw.prev_max
        )
        SELECT
            s.ticker,
            s.price_sar,
            s.snapshot_date,
            s.raw_json,
            s.nav_discount_pct,
            s.distribution_per_unit_sar,
            pw.prev_price,
            pw.prev_date
        FROM reit_snapshots s
        JOIN latest l ON s.ticker = l.ticker AND s.snapshot_date = l.max_date
        LEFT JOIN prev_week pw ON pw.ticker = s.ticker
        ORDER BY s.ticker
    """))
    db_rows = rows.fetchall()

    if not db_rows:
        return [], "No REIT snapshot data available."

    structured: list[dict[str, Any]] = []
    lines: list[str] = []

    industrial_lines = ["INDUSTRIAL (priority tracking):"]
    other_lines = ["ALL LISTED REITs:"]

    for r in db_rows:
        raw = r.raw_json if isinstance(r.raw_json, dict) else {}
        name = raw.get("name", r.ticker)
        price = float(r.price_sar) if r.price_sar is not None else None
        prev_price = float(r.prev_price) if r.prev_price is not None else None
        wow_delta = round(price - prev_price, 4) if price and prev_price else None
        wow_pct = round((wow_delta / prev_price) * 100, 2) if wow_delta and prev_price else None
        nav_disc = float(r.nav_discount_pct) if r.nav_discount_pct is not None else None
        dist = float(r.distribution_per_unit_sar) if r.distribution_per_unit_sar is not None else None
        is_industrial = r.ticker in INDUSTRIAL_TICKERS

        row_dict = {
            "ticker": r.ticker,
            "name": name,
            "price_sar": price,
            "prior_price_sar": prev_price,
            "wow_delta_sar": wow_delta,
            "wow_delta_pct": wow_pct,
            "nav_discount_pct": nav_disc,
            "distribution_sar": dist,
            "snapshot_date": str(r.snapshot_date),
            "is_industrial": is_industrial,
        }
        structured.append(row_dict)

        # Format for Opus
        price_str = f"SAR {price:.2f}" if price else "N/A"
        wow_str = (
            f"WoW {wow_delta:+.2f} ({wow_pct:+.1f}%)" if wow_delta is not None else "WoW Δ n/a (no prior-week snapshot)"
        )
        nav_str = f"NAV discount {nav_disc:+.1f}%" if nav_disc is not None else "NAV not available"
        dist_str = f"distribution SAR {dist:.2f}/unit" if dist else ""
        parts = [f"{r.ticker} ({name}): {price_str} · {wow_str} · {nav_str}"]
        if dist_str:
            parts.append(dist_str)
        line = "  " + " · ".join(parts)

        if is_industrial:
            industrial_lines.append(line)
        else:
            other_lines.append(line)

    snapshot_date = db_rows[0].snapshot_date if db_rows else "unknown"
    lines = industrial_lines + [""] + other_lines + [f"\nData as of: {snapshot_date} (15-min delayed via yfinance)"]

    return structured, "\n".join(lines)


# ── Transaction section ─────────────────────────────────────────────────────


async def _transaction_section(session: AsyncSession, week_start: date, week_ending: date) -> str:
    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.transaction_date >= week_start,
            Transaction.transaction_date <= week_ending,
        )
        .order_by(Transaction.transaction_date.desc())
        .limit(50)
    )
    txns = list(result.scalars())

    if not txns:
        return (
            "No transaction data available for this period. "
            "REGA direct transaction data is pending a data sharing agreement "
            "(Open Data request submitted 18 Apr 2026; expected response 30-90 days). "
            "This brief relies on secondary sources: Tadawul REIT prices (yfinance), "
            "Aqar warehouse listings (leading indicator for industrial rents), "
            "Knight Frank / CBRE / JLL research reports (survey-based rent benchmarks), "
            "Argaam news aggregates, and government tender flows (Etimad)."
        )

    by_type: dict[str, list] = {}
    for t in txns:
        by_type.setdefault(t.property_type, []).append(t)

    lines = [f"Transactions {week_start} - {week_ending} ({len(txns)} records):"]
    for ptype, rows in by_type.items():
        total_value = sum(r.price_sar for r in rows)
        avg_area = (
            sum(r.area_sqm for r in rows if r.area_sqm) / len([r for r in rows if r.area_sqm])
            if any(r.area_sqm for r in rows)
            else None
        )
        lines.append(
            f"  {ptype}: {len(rows)} transactions, "
            f"total SAR {total_value:,.0f}"
            + (f", avg area {avg_area:,.0f} sqm" if avg_area else "")
        )
    return "\n".join(lines)


# ── Listing section ─────────────────────────────────────────────────────────


async def _listing_section(session: AsyncSession) -> tuple[dict, str]:
    """Returns (stats_dict, formatted_text) for warehouse listings."""
    result = await session.execute(
        select(Listing)
        .where(Listing.is_active == True, Listing.listing_type == "lease")  # noqa: E712
        .order_by(Listing.listed_at.desc())
        .limit(100)
    )
    listings = list(result.scalars())

    if not listings:
        return {}, (
            "No warehouse listing data available. "
            "Aqar scraper requires Cloudflare cookie session to be established."
        )

    by_district: dict[str, list] = {}
    for lst in listings:
        key = lst.district or "Unknown district"
        by_district.setdefault(key, []).append(lst)

    all_rents = [lst.rent_sar_annual for lst in listings if lst.rent_sar_annual]
    all_areas = [lst.area_sqm for lst in listings if lst.area_sqm]
    avg_rent = sum(all_rents) / len(all_rents) if all_rents else None
    avg_area = sum(all_areas) / len(all_areas) if all_areas else None
    implied_rate = round(avg_rent / avg_area, 1) if avg_rent and avg_area else None

    stats = {
        "count": len(listings),
        "avg_rent_sar_yr": round(avg_rent) if avg_rent else None,
        "avg_area_sqm": round(avg_area) if avg_area else None,
        "implied_sar_sqm_yr": implied_rate,
        "districts": list(by_district.keys()),
        "district_count": len(by_district),
    }

    lines = [f"Active warehouse leases ({len(listings)} listings):"]
    for district, rows in sorted(by_district.items()):
        rents = [r.rent_sar_annual for r in rows if r.rent_sar_annual]
        d_avg_rent = sum(rents) / len(rents) if rents else None
        areas = [r.area_sqm for r in rows if r.area_sqm]
        d_avg_area = sum(areas) / len(areas) if areas else None
        lines.append(
            f"  {district}: {len(rows)} listings"
            + (f", avg rent SAR {d_avg_rent:,.0f}/yr" if d_avg_rent else "")
            + (f", avg area {d_avg_area:,.0f} sqm" if d_avg_area else "")
        )

    if avg_rent and avg_area:
        lines.append(f"\nMarket-wide (all districts): avg SAR {avg_rent:,.0f}/yr, avg {avg_area:,.0f} sqm, implied SAR {implied_rate}/sqm/yr")

    return stats, "\n".join(lines)


# ── Rent index section ──────────────────────────────────────────────────────


async def _rent_index_section(session: AsyncSession) -> str:
    result = await session.execute(
        select(RentIndex)
        .where(RentIndex.property_type.in_(["warehouse", "industrial_land", "logistics"]))
        .order_by(RentIndex.period.desc(), RentIndex.source_priority.asc())
        .limit(30)
    )
    rows = list(result.scalars())

    if not rows:
        return (
            "No rent index data available. "
            "Download and extract Knight Frank / CBRE / JLL reports."
        )

    lines = ["Research report rent indices (SAR/sqm/year):"]
    for r in rows:
        district = r.district or "Riyadh (market-wide)"
        rent = f"SAR {r.rent_sar_sqm_annual:,.0f}/sqm/yr" if r.rent_sar_sqm_annual else "N/A"
        yoy = f" ({r.yoy_change_pct:+.1f}% YoY)" if r.yoy_change_pct is not None else ""
        vac = f", vacancy {r.vacancy_pct:.1f}%" if r.vacancy_pct is not None else ""
        lines.append(
            f"  [{r.period}] {district} · {r.property_type} · {rent}{yoy}{vac} [{r.source}]"
        )
    return "\n".join(lines)


# ── Typed fact tables ───────────────────────────────────────────────────────


async def _typed_facts_section(
    session: AsyncSession, week_start: date, week_ending: date
) -> tuple[str, dict]:
    """Pull all promoted facts from 8 typed tables created within the 7-day window.

    Returns (formatted_text_for_opus, structured_dict_for_template).
    Confidence >= 4 only (all rows in typed tables satisfy this by routing rules).
    """
    start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=UTC)
    end_dt = datetime.combine(week_ending, datetime.max.time()).replace(tzinfo=UTC)

    sections: list[str] = []
    structured: dict[str, list] = {}

    # ── macro_signals ────────────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT indicator, period, value, direction, magnitude, source_citation, confidence
        FROM macro_signals
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC, indicator
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"MACRO SIGNALS ({len(rows)} facts, conf ≥ 4):"]
        structured["macro_signals"] = []
        for row in rows:
            val = f" | value={row.value}" if row.value is not None else ""
            direction = f" | {row.direction}" if row.direction else ""
            mag = f" | {row.magnitude}" if row.magnitude else ""
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            lines.append(f"  [c={row.confidence}] {row.indicator} | period={row.period}{val}{direction}{mag}{cite}")
            structured["macro_signals"].append({
                "indicator": row.indicator, "period": row.period,
                "value": str(row.value) if row.value is not None else None,
                "direction": row.direction, "magnitude": row.magnitude,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── regulatory_events ────────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT event_type, authority, scope, effective_date, summary, source_citation, confidence
        FROM regulatory_events
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"REGULATORY EVENTS ({len(rows)} facts):"]
        structured["regulatory_events"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            eff = f" | effective: {row.effective_date}" if row.effective_date else ""
            lines.append(f"  [c={row.confidence}] {row.event_type} | {row.authority} | scope={row.scope}{eff} | {row.summary}{cite}")
            structured["regulatory_events"].append({
                "event_type": row.event_type, "authority": row.authority,
                "scope": row.scope, "effective_date": row.effective_date,
                "summary": row.summary, "citation": row.source_citation,
                "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── demand_signals ───────────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT sector, metric, period, value, geography, source_citation, confidence
        FROM demand_signals
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC, sector
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"DEMAND SIGNALS ({len(rows)} facts):"]
        structured["demand_signals"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            geo = f" | geo={row.geography}" if row.geography else ""
            val = f" | value={row.value}" if row.value else ""
            lines.append(f"  [c={row.confidence}] {row.sector} | {row.metric} | period={row.period}{val}{geo}{cite}")
            structured["demand_signals"].append({
                "sector": row.sector, "metric": row.metric, "period": row.period,
                "value": row.value, "geography": row.geography,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── capital_markets_events ───────────────────────────────────────────
    r = await session.execute(text("""
        SELECT event_type, entity, ticker_if_listed, value_sar, source_citation, confidence
        FROM capital_markets_events
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC, entity
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"CAPITAL MARKETS EVENTS ({len(rows)} facts):"]
        structured["capital_markets_events"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            val = f" | SAR {row.value_sar:,.0f}" if row.value_sar else ""
            ticker = f" | ticker={row.ticker_if_listed}" if row.ticker_if_listed else ""
            lines.append(f"  [c={row.confidence}] {row.event_type} | {row.entity}{ticker}{val}{cite}")
            structured["capital_markets_events"].append({
                "event_type": row.event_type, "entity": row.entity,
                "ticker_if_listed": row.ticker_if_listed,
                "value_sar": float(row.value_sar) if row.value_sar else None,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── supply_events ────────────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT event_type, developer, project_name, location_description,
               district_guess, asset_class, gfa_sqm, value_sar,
               expected_completion_date, source_citation, confidence
        FROM supply_events
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"SUPPLY EVENTS ({len(rows)} facts):"]
        structured["supply_events"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            val = f" | SAR {row.value_sar:,.0f}" if row.value_sar else ""
            gfa = f" | GFA {row.gfa_sqm:,.0f}sqm" if row.gfa_sqm else ""
            dev = f" | dev={row.developer}" if row.developer else ""
            proj = f" | project={row.project_name}" if row.project_name else ""
            lines.append(f"  [c={row.confidence}] {row.event_type}{dev}{proj} | {row.location_description} | {row.asset_class}{gfa}{val}{cite}")
            structured["supply_events"].append({
                "event_type": row.event_type, "developer": row.developer,
                "project_name": row.project_name,
                "location_description": row.location_description,
                "district_guess": row.district_guess, "asset_class": row.asset_class,
                "gfa_sqm": float(row.gfa_sqm) if row.gfa_sqm else None,
                "value_sar": float(row.value_sar) if row.value_sar else None,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── infrastructure_events ────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT project, infra_type, phase, location, completion_date, source_citation, confidence
        FROM infrastructure_events
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"INFRASTRUCTURE EVENTS ({len(rows)} facts):"]
        structured["infrastructure_events"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            comp = f" | completion={row.completion_date}" if row.completion_date else ""
            lines.append(f"  [c={row.confidence}] {row.infra_type} | {row.project} | {row.location} | phase={row.phase}{comp}{cite}")
            structured["infrastructure_events"].append({
                "project": row.project, "infra_type": row.infra_type,
                "phase": row.phase, "location": row.location,
                "completion_date": row.completion_date,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── tenant_signals ───────────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT tenant_name, industry, event_type, geography, source_citation, confidence
        FROM tenant_signals
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC, tenant_name
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"TENANT SIGNALS ({len(rows)} facts):"]
        structured["tenant_signals"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            geo = f" | geo={row.geography}" if row.geography else ""
            lines.append(f"  [c={row.confidence}] {row.tenant_name} | {row.industry} | {row.event_type}{geo}{cite}")
            structured["tenant_signals"].append({
                "tenant_name": row.tenant_name, "industry": row.industry,
                "event_type": row.event_type, "geography": row.geography,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    # ── market_commentary ────────────────────────────────────────────────
    r = await session.execute(text("""
        SELECT source_authority, topic, quote_under_15_words, source_citation, confidence
        FROM market_commentary
        WHERE created_at >= :s AND created_at <= :e
        ORDER BY confidence DESC, source_authority
    """), {"s": start_dt, "e": end_dt})
    rows = r.fetchall()
    if rows:
        lines = [f"MARKET COMMENTARY ({len(rows)} facts):"]
        structured["market_commentary"] = []
        for row in rows:
            cite = f' | citation: "{row.source_citation}"' if row.source_citation else ""
            lines.append(f'  [c={row.confidence}] {row.source_authority} | {row.topic} | quote: "{row.quote_under_15_words}"{cite}')
            structured["market_commentary"].append({
                "source_authority": row.source_authority, "topic": row.topic,
                "quote": row.quote_under_15_words,
                "citation": row.source_citation, "confidence": row.confidence,
            })
        sections.append("\n".join(lines))

    total = sum(len(v) for v in structured.values())
    header = f"EXTRACTED FACTS FROM NEWS ARTICLES ({total} total, confidence ≥ 4):\n"
    return header + "\n\n".join(sections), structured


# ── News section ────────────────────────────────────────────────────────────


async def _news_section(session: AsyncSession, week_start: date, week_ending: date) -> str:
    """Return high-relevance articles with non-KSA content filtered out.

    Filters:
      - Active sources only (argaam_en, argaam_ar, logistics_me)
      - Relevance score >= 0.5
      - Title must not contain UAE/Gulf geography tokens
    """
    week_start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=UTC)
    week_end_dt = datetime.combine(week_ending, datetime.max.time()).replace(tzinfo=UTC)

    result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.published_at >= week_start_dt,
            NewsArticle.published_at <= week_end_dt,
            NewsArticle.relevance_score >= 0.5,
            NewsArticle.source.in_(_ACTIVE_SOURCES),
        )
        .order_by(NewsArticle.relevance_score.desc())
        .limit(20)
    )
    articles = list(result.scalars())

    if not articles:
        # Fall back to most recent relevant articles regardless of date
        result2 = await session.execute(
            select(NewsArticle)
            .where(
                NewsArticle.relevance_score >= 0.5,
                NewsArticle.source.in_(_ACTIVE_SOURCES),
            )
            .order_by(NewsArticle.relevance_score.desc())
            .limit(15)
        )
        articles = list(result2.scalars())
        if not articles:
            return (
                "No news data available. "
                "Run news scraper with SCRAPER_LIVE_MODE=true and wait for triage pass."
            )

    # Filter non-KSA content by title geography tokens
    def _is_ksa(article: NewsArticle) -> bool:
        title = (article.title_en or article.title_ar or "").lower()
        return not any(tok.lower() in title for tok in _NON_KSA_TOKENS)

    articles = [a for a in articles if _is_ksa(a)]
    if not articles:
        return "No KSA-relevant news after geography filter."

    lines = [f"Relevant news ({len(articles)} articles, relevance ≥ 0.5, KSA-filtered):"]
    for a in articles:
        title = a.title_en or a.title_ar or "(no title)"
        score = f"{a.relevance_score:.2f}" if a.relevance_score is not None else "?"
        pub = a.published_at.strftime("%-d %b %Y") if a.published_at else "date unknown"
        source = a.source or "unknown"
        lines.append(f"\n  [{score}] [{pub}] [{source}] {title}")
    return "\n".join(lines)


# ── Tender section ──────────────────────────────────────────────────────────


async def _tender_section(session: AsyncSession, week_start: date, week_ending: date) -> str:
    week_start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=UTC)
    week_end_dt = datetime.combine(week_ending, datetime.max.time()).replace(tzinfo=UTC)

    result = await session.execute(
        select(Tender)
        .where(
            Tender.published_at >= week_start_dt,
            Tender.published_at <= week_end_dt,
        )
        .order_by(Tender.value_sar.desc().nullslast())
        .limit(10)
    )
    tenders = list(result.scalars())

    if not tenders:
        result2 = await session.execute(
            select(Tender)
            .where(Tender.deadline_at >= datetime.now(UTC))
            .order_by(Tender.value_sar.desc().nullslast())
            .limit(5)
        )
        tenders = list(result2.scalars())
        if not tenders:
            return (
                "No tender data available. "
                "Configure ETIMAD_CLIENT_ID / ETIMAD_CLIENT_SECRET in .env.local to enable."
            )

    lines = [f"Etimad government tenders ({len(tenders)}):"]
    for t in tenders:
        title = t.title_en or t.title_ar or "(no title)"
        entity = t.entity_name or "Unknown entity"
        value = f"SAR {t.value_sar:,.0f}" if t.value_sar else "value undisclosed"
        deadline = f"deadline {t.deadline_at.date()}" if t.deadline_at else "no deadline"
        lines.append(f"  [{entity}] {title} — {value} · {deadline}")
    return "\n".join(lines)


# ── Data notes ──────────────────────────────────────────────────────────────


def _data_notes() -> str:
    return (
        "Data quality notes:\n"
        "- REIT prices are 15-min delayed via yfinance (Tadawul)\n"
        "- NAV, distribution yield, and occupancy not yet available (requires PDF extraction from CMA filings)\n"
        "- REGA direct transaction data pending Open Data agreement "
        "(submitted 18 Apr 2026; expected 30-90 days)\n"
        "- Listing data: 20 active Aqar leases, Industrial City only; "
        "other districts not yet scraped\n"
        "- Typed facts (macro_signals, regulatory_events, etc.) sourced from Argaam AR/EN "
        "and Logistics Middle East; confidence >= 4 only\n"
        "- Acknowledge all gaps explicitly in the brief"
    )
