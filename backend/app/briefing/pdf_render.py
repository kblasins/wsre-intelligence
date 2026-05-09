"""Phase 4b — Playwright PDF render for the weekly brief.

Renders brief_json (structured dict from Opus + authoritative context data) to a
styled PDF using headless Chromium. No raw JSON, no Markdown pipes appear in output.

Design vocabulary: Knight Frank / CBRE MarketView institutional research.
  - IBM Plex Sans body, IBM Plex Mono numerics
  - Navy (#1a3a5c) section rules and accents, all else grayscale
  - Tabular-nums for all price/percent columns
  - Page headers/footers via Playwright display_header_footer
  - A4, 22mm top, 20mm bottom, 15mm sides
"""

from __future__ import annotations

import html as _html_module
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.brief import WeeklyBrief

log = structlog.get_logger(__name__)

_NAVY = "#1a3a5c"
_DARK = "#1a1a1a"
_MID = "#555555"
_LIGHT = "#888888"
_RULE = "#d0d7de"
_ACCENT_BG = "#f0f4f8"

# ── HTML helpers ─────────────────────────────────────────────────────────────


def _e(s: Any) -> str:
    """HTML-escape a value for safe rendering."""
    return _html_module.escape(str(s)) if s is not None else ""


def _fmt_sar(val: Any, decimals: int = 2) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
        if decimals == 0:
            return f"SAR {v:,.0f}"
        return f"SAR {v:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(val)


def _fmt_pct(val: Any, sign: bool = False) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
        return f"{v:+.2f}%" if sign else f"{v:.2f}%"
    except (TypeError, ValueError):
        return str(val)


def _na(val: Any, fallback: str = "—") -> str:
    return _e(val) if val is not None and str(val).strip() not in ("", "None") else fallback


# ── CSS ──────────────────────────────────────────────────────────────────────

_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap');

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'IBM Plex Sans', Helvetica, Arial, sans-serif;
  font-size: 9.5pt;
  line-height: 1.55;
  color: {_DARK};
  background: #ffffff;
}}

/* ── Title block ── */
.title-block {{
  margin-bottom: 20pt;
  padding-bottom: 12pt;
  border-bottom: 1.5pt solid {_NAVY};
}}
.title-brief {{
  font-size: 16pt;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: {_DARK};
  line-height: 1.2;
}}
.title-sub {{
  font-size: 9pt;
  font-weight: 300;
  color: {_MID};
  margin-top: 3pt;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}}
.title-confidential {{
  font-size: 7.5pt;
  font-weight: 600;
  color: {_LIGHT};
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-top: 6pt;
}}

/* ── Section headers ── */
h2 {{
  font-size: 8.5pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: {_NAVY};
  border-bottom: 0.5pt solid {_NAVY};
  padding-bottom: 3pt;
  margin: 20pt 0 9pt;
}}
h2:first-of-type {{ margin-top: 0; }}

/* ── Body text ── */
p {{
  margin: 0 0 6pt;
}}
.data-gap {{
  font-size: 8.5pt;
  font-style: italic;
  color: {_LIGHT};
  margin: 4pt 0;
}}
.data-gap::before {{ content: "Data gap: "; font-weight: 500; }}

/* ── Tables ── */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 8pt 0 12pt;
  font-size: 8.5pt;
}}
thead th {{
  background: {_ACCENT_BG};
  font-weight: 600;
  font-size: 7.5pt;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: {_MID};
  padding: 5pt 8pt;
  border-bottom: 1pt solid {_RULE};
  border-top: 1pt solid {_RULE};
  text-align: left;
}}
thead th.num {{ text-align: right; }}
tbody td {{
  padding: 4.5pt 8pt;
  border-bottom: 0.5pt solid {_RULE};
  vertical-align: top;
  color: {_DARK};
}}
tbody td.num {{
  text-align: right;
  font-family: 'IBM Plex Mono', 'Courier New', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 8pt;
}}
tbody td.label {{ font-weight: 500; }}
tbody tr:last-child td {{ border-bottom: 1pt solid {_RULE}; }}
.pos {{ color: #1a6b2d; }}
.neg {{ color: #a61c00; }}
.na  {{ color: {_LIGHT}; font-style: italic; }}

/* ── News items ── */
.news-item {{
  margin: 8pt 0;
  padding: 8pt 10pt;
  border-left: 2pt solid {_RULE};
}}
.news-item:first-child {{ border-left-color: {_NAVY}; }}
.news-score {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 7.5pt;
  color: {_LIGHT};
  display: inline-block;
  margin-right: 6pt;
}}
.news-headline {{
  font-weight: 500;
  font-size: 9pt;
}}
.news-source {{
  font-size: 7.5pt;
  color: {_LIGHT};
  margin-left: 4pt;
}}
.news-impl {{
  margin-top: 3pt;
  font-size: 8.5pt;
  color: {_MID};
}}
.news-citation {{
  margin-top: 3pt;
  font-size: 8pt;
  font-style: italic;
  color: {_MID};
  padding-left: 8pt;
  border-left: 1.5pt solid {_RULE};
}}

/* ── Highlights (macro / regulatory / supply / demand) ── */
.highlight-item {{
  margin: 6pt 0;
  padding: 6pt 10pt;
  background: {_ACCENT_BG};
  border-radius: 1pt;
}}
.highlight-label {{
  font-weight: 600;
  font-size: 8.5pt;
  color: {_DARK};
}}
.highlight-meta {{
  font-size: 8pt;
  color: {_MID};
  display: inline-block;
  margin-left: 6pt;
}}
.highlight-impl {{
  font-size: 8.5pt;
  color: {_MID};
  margin-top: 2pt;
}}
.highlight-citation {{
  font-size: 7.5pt;
  font-style: italic;
  color: {_LIGHT};
  margin-top: 2pt;
}}

/* ── Watch list ── */
.watch-item {{
  margin: 8pt 0;
  padding: 8pt 10pt;
  border-left: 2.5pt solid {_NAVY};
  background: #fafbfc;
}}
.watch-title {{ font-weight: 600; font-size: 9pt; color: {_DARK}; }}
.watch-trigger {{
  margin-top: 3pt;
  font-size: 8.5pt;
  color: {_MID};
}}
.watch-trigger strong {{ color: {_DARK}; }}
.watch-timeline {{
  margin-top: 3pt;
  font-size: 8pt;
  font-family: 'IBM Plex Mono', monospace;
  color: {_NAVY};
}}

/* ── Summary box ── */
.exec-summary {{
  padding: 10pt 12pt;
  border: 0.5pt solid {_NAVY};
  border-left: 3pt solid {_NAVY};
  background: {_ACCENT_BG};
  margin-bottom: 4pt;
}}
.exec-summary p {{ margin: 0; font-size: 9.5pt; }}

/* ── Print ── */
@media print {{
  h2 {{ break-after: avoid; }}
  .watch-item, .news-item, .highlight-item {{ break-inside: avoid; }}
  tbody tr {{ break-inside: avoid; }}
  .title-block {{ break-after: avoid; }}
}}
"""

# ── Section builders ─────────────────────────────────────────────────────────


def _section(title: str, body: str) -> str:
    return f'<h2>{_e(title)}</h2>\n{body}\n'


def _data_gaps(gaps: list | None) -> str:
    if not gaps:
        return ""
    return "".join(f'<p class="data-gap">{_e(g)}</p>' for g in gaps)


def _reit_table(reit_rows: list[dict]) -> str:
    if not reit_rows:
        return '<p class="data-gap">No REIT snapshot data.</p>'

    industrial = [r for r in reit_rows if r.get("is_industrial")]
    others = [r for r in reit_rows if not r.get("is_industrial")]

    def _rows(items: list[dict]) -> str:
        out = []
        for r in items:
            price = f"{r['price_sar']:.2f}" if r.get("price_sar") else "—"
            prev = f"{r['prior_price_sar']:.2f}" if r.get("prior_price_sar") else "—"

            wow_val = r.get("wow_delta_sar")
            wow_pct = r.get("wow_delta_pct")
            if wow_val is not None:
                sign_class = "pos" if wow_val >= 0 else "neg"
                wow_str = f'<span class="{sign_class}">{wow_val:+.2f} ({wow_pct:+.1f}%)</span>'
            else:
                wow_str = '<span class="na">n/a</span>'

            nav = f"{r['nav_discount_pct']:+.1f}%" if r.get("nav_discount_pct") is not None else '<span class="na">—</span>'
            dist = f"SAR {r['distribution_sar']:.2f}" if r.get("distribution_sar") else '<span class="na">—</span>'

            out.append(f"""
<tr>
  <td class="label">{_e(r['ticker'])}</td>
  <td>{_e(r['name'])}</td>
  <td class="num">SAR {_e(price)}</td>
  <td class="num">{_e(prev)}</td>
  <td class="num">{wow_str}</td>
  <td class="num">{nav}</td>
  <td class="num">{dist}</td>
</tr>""")
        return "".join(out)

    table = f"""
<table>
<thead><tr>
  <th>Ticker</th><th>Name</th>
  <th class="num">Close</th><th class="num">Prior Week</th>
  <th class="num">WoW Δ</th><th class="num">NAV Discount</th><th class="num">Distribution</th>
</tr></thead>
<tbody>"""

    if industrial:
        table += f'<tr><td colspan="7" style="font-size:7.5pt;font-weight:600;color:{_NAVY};padding:6pt 8pt 2pt;text-transform:uppercase;letter-spacing:.08em;">Industrial Focus</td></tr>'
        table += _rows(industrial)

    if others:
        table += f'<tr><td colspan="7" style="font-size:7.5pt;font-weight:600;color:{_MID};padding:6pt 8pt 2pt;text-transform:uppercase;letter-spacing:.08em;">Broader REIT Universe</td></tr>'
        table += _rows(others)

    table += "</tbody></table>"

    # Snapshot date footnote
    if reit_rows:
        snap_date = reit_rows[0].get("snapshot_date", "")
        table += f'<p style="font-size:7.5pt;color:{_LIGHT};margin-top:-6pt;">Data as of {_e(snap_date)} · 15-minute delayed via yfinance · NAV requires CMA filing extraction</p>'

    return table


def _listing_table(stats: dict) -> str:
    if not stats:
        return '<p class="data-gap">No Aqar listing data available.</p>'

    count = stats.get("count", 0)
    avg_rent = stats.get("avg_rent_sar_yr")
    avg_area = stats.get("avg_area_sqm")
    implied = stats.get("implied_sar_sqm_yr")
    districts = stats.get("districts", [])

    rows = [
        ("Active listings", f"{count}"),
        ("Avg. asking rent", f"SAR {avg_rent:,.0f}/yr" if avg_rent else "—"),
        ("Avg. unit area", f"{avg_area:,.0f} sqm" if avg_area else "—"),
        ("Implied rate", f"SAR {implied}/sqm/yr" if implied else "—"),
        ("Districts covered", ", ".join(districts) if districts else "—"),
    ]

    trs = "".join(
        f"<tr><td class='label' style='width:45%'>{_e(k)}</td><td class='num'>{_e(v)}</td></tr>"
        for k, v in rows
    )
    return f"""<table><thead><tr><th>Metric</th><th class="num">Value</th></tr></thead><tbody>{trs}</tbody></table>"""


def _news_items(items: list[dict]) -> str:
    if not items:
        return '<p class="data-gap">No KSA-relevant news items this week.</p>'
    out = []
    for item in items:
        score_html = f'<span class="news-score">[{item.get("score", 0):.2f}]</span>' if item.get("score") is not None else ""
        source_html = f'<span class="news-source">— {_e(item.get("source", ""))}, {_e(item.get("date", ""))}</span>' if item.get("source") else ""
        impl_html = f'<div class="news-impl">{_e(item.get("implication", ""))}</div>' if item.get("implication") else ""
        cite = item.get("citation")
        cite_html = f'<div class="news-citation">"{_e(cite)}"</div>' if cite else ""
        out.append(f"""<div class="news-item">
<div>{score_html}<span class="news-headline">{_e(item.get("headline", ""))}</span>{source_html}</div>
{impl_html}{cite_html}
</div>""")
    return "\n".join(out)


def _highlight_items(items: list[dict], label_key: str, value_key: str = "", meta_key: str = "") -> str:
    if not items:
        return '<p class="data-gap">No items recorded.</p>'
    out = []
    for item in items:
        label = item.get(label_key, "")
        value = item.get(value_key, "") if value_key else ""
        meta = item.get(meta_key, "") if meta_key else ""
        impl = item.get("implication", "")
        cite = item.get("citation")

        meta_parts = []
        if value:
            meta_parts.append(_e(value))
        if meta:
            meta_parts.append(_e(meta))
        meta_html = f'<span class="highlight-meta">{" · ".join(meta_parts)}</span>' if meta_parts else ""
        impl_html = f'<div class="highlight-impl">{_e(impl)}</div>' if impl else ""
        cite_html = f'<div class="highlight-citation">"{_e(cite)}"</div>' if cite else ""

        out.append(f"""<div class="highlight-item">
<span class="highlight-label">{_e(label)}</span>{meta_html}
{impl_html}{cite_html}
</div>""")
    return "\n".join(out)


def _watch_list(items: list[dict]) -> str:
    if not items:
        return '<p class="data-gap">No watch items.</p>'
    out = []
    for i, item in enumerate(items, 1):
        out.append(f"""<div class="watch-item">
<div class="watch-title">{i}. {_e(item.get("item", ""))}</div>
<div class="watch-trigger"><strong>Trigger:</strong> {_e(item.get("trigger", ""))}</div>
<div class="watch-timeline">{_e(item.get("timeline", ""))}</div>
</div>""")
    return "\n".join(out)


# ── Full HTML document ────────────────────────────────────────────────────────


def _build_pdf_html(brief: WeeklyBrief) -> str:
    """Render brief_json to print-ready HTML. No raw JSON appears in output."""
    d = brief.brief_json or {}
    week = d.get("_week_ending_long") or brief.week_ending.strftime("%-d %B %Y")
    model = d.get("_model_id", brief.model_id)
    cost = d.get("_cost_usd", float(brief.cost_usd))
    reit_rows = d.get("_reit_rows", [])
    listing_stats = d.get("_listing_stats", {})

    # ── Individual sections ──────────────────────────────────────────────

    # 1. Executive summary
    exec_sum = d.get("executive_summary") or "Executive summary not available."
    s1 = _section("1. Executive Summary",
        f'<div class="exec-summary"><p>{_e(exec_sum)}</p></div>')

    # 2. Industrial REIT Performance
    reit_commentary = d.get("reit_commentary") or ""
    reit_gaps = d.get("reit_data_gaps") or []
    s2 = _section("2. Industrial REIT Performance",
        _reit_table(reit_rows)
        + (f"<p>{_e(reit_commentary)}</p>" if reit_commentary else "")
        + _data_gaps(reit_gaps))

    # 3. Transactions
    txn_commentary = d.get("transaction_commentary") or ""
    txn_gaps = d.get("transaction_data_gaps") or []
    s3 = _section("3. Transactions",
        (f"<p>{_e(txn_commentary)}</p>" if txn_commentary else "")
        + _data_gaps(txn_gaps))

    # 4. Warehouse Market
    wh_commentary = d.get("warehouse_commentary") or ""
    wh_gaps = d.get("warehouse_data_gaps") or []
    supply = d.get("supply_highlights") or []
    s4 = _section("4. Warehouse Market",
        _listing_table(listing_stats)
        + (f"<p>{_e(wh_commentary)}</p>" if wh_commentary else "")
        + (_section_subsection("Supply Pipeline", _highlight_items(supply, "description", "event_type", "location")) if supply else "")
        + _data_gaps(wh_gaps))

    # 5. News & Intelligence
    news_items = d.get("news_intelligence") or []
    s5 = _section("5. News & Intelligence", _news_items(news_items))

    # 6. Macro Indicators
    macro = d.get("macro_highlights") or []
    s6 = _section("6. Macro Indicators",
        _highlight_items(macro, "indicator", "value", "period") if macro
        else '<p class="data-gap">No macro indicators extracted this week.</p>')

    # 7. Regulatory Updates
    reg = d.get("regulatory_highlights") or []
    s7 = _section("7. Regulatory Updates",
        _highlight_items(reg, "authority", "summary", "effective_date") if reg
        else '<p class="data-gap">No regulatory updates extracted this week.</p>')

    # 8. Demand Signals (if present)
    demand = d.get("demand_highlights") or []
    s8 = (_section("8. Demand Signals",
        _highlight_items(demand, "sector", "value", "metric")) if demand else "")

    # 9. Watch List
    s_watch = _section("Watch List", _watch_list(d.get("watch_list") or []))

    body = s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8 + s_watch

    # ── Sources footnote ─────────────────────────────────────────────────
    sources_note = (
        "Sources: Tadawul via yfinance (15-min delayed) · Aqar warehouse listings · "
        "Argaam EN/AR news aggregates · Logistics Middle East · "
        "Knight Frank / CBRE / JLL research reports · Etimad government tenders. "
        "REGA transaction data pending Open Data agreement (submitted 18 Apr 2026)."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>White Star — Weekly Brief {_e(week)}</title>
<style>{_CSS}</style>
</head>
<body>

<div class="title-block">
  <div class="title-brief">Riyadh Industrial Real Estate</div>
  <div class="title-sub">Weekly Market Intelligence Brief · Week Ending {_e(week)}</div>
  <div class="title-confidential">Confidential · White Star Real Estate</div>
</div>

{body}

<div style="margin-top:24pt;padding-top:8pt;border-top:0.5pt solid {_RULE};font-size:7.5pt;color:{_LIGHT};">
  {_e(sources_note)}
</div>

</body>
</html>"""


def _section_subsection(title: str, body: str) -> str:
    return f'<p style="font-weight:600;font-size:8.5pt;color:{_MID};margin:10pt 0 4pt;text-transform:uppercase;letter-spacing:.06em;">{_e(title)}</p>\n{body}\n'


# ── Playwright render ─────────────────────────────────────────────────────────


async def render_brief_pdf(brief: WeeklyBrief, session: AsyncSession) -> str | None:
    """Render brief to PDF, upload to blob storage, update brief.pdf_uri.

    Returns the blob URI string on success, None on failure (non-fatal).
    Requires: playwright install chromium
    """
    try:
        from playwright.async_api import async_playwright

        from app.core.storage import upload_raw
    except ImportError:
        log.warning("pdf_render_skipped", reason="playwright_not_available")
        return None

    html = _build_pdf_html(brief)
    week = brief.week_ending.strftime("%-d %B %Y")
    cost_str = f"${float(brief.cost_usd):.4f}"

    header_tpl = (
        f'<div style="font-size:7pt;font-family:IBM Plex Sans,Helvetica,sans-serif;'
        f'width:100%;padding:0 15mm;display:flex;justify-content:space-between;color:#888;margin-top:4mm;">'
        f'<span>White Star · Riyadh Industrial Market Intelligence</span>'
        f'<span>Week ending {week}</span></div>'
    )
    footer_tpl = (
        f'<div style="font-size:7pt;font-family:IBM Plex Sans,Helvetica,sans-serif;'
        f'width:100%;padding:0 15mm;display:flex;justify-content:space-between;color:#aaa;margin-bottom:4mm;">'
        f'<span>Confidential · White Star Real Estate</span>'
        f'<span><span class="pageNumber"></span> / <span class="totalPages"></span>'
        f' &nbsp;·&nbsp; {brief.model_id} &nbsp;·&nbsp; {cost_str} API cost</span></div>'
    )

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")

            pdf_bytes = await page.pdf(
                format="A4",
                margin={"top": "22mm", "right": "15mm", "bottom": "20mm", "left": "15mm"},
                print_background=True,
                display_header_footer=True,
                header_template=header_tpl,
                footer_template=footer_tpl,
            )
            await browser.close()
    except Exception:
        log.exception("pdf_render_failed", week=str(brief.week_ending))
        return None

    uri, _ = await upload_raw(
        pdf_bytes, "brief", "pdf",
        content_type="application/pdf",
        ts=datetime.now(UTC),
    )

    brief.pdf_uri = uri
    await session.commit()

    log.info("pdf_rendered", week=str(brief.week_ending), uri=uri, size_kb=len(pdf_bytes) // 1024)
    return uri
