"""Warsaw weekly brief — Playwright PDF renderer.

Renders brief_json (Warsaw Opus output + authoritative context data) to a
styled A4 PDF. Warsaw branding: navy, IBM Plex Sans, institutional research
voice. Polish diacritics rendered natively by Chromium.

Design vocabulary: Knight Frank / CBRE MarketView research note.
  - IBM Plex Sans body, IBM Plex Mono numerics (tabular-nums)
  - Navy (#002060) section rules and accents
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

_NAVY = "#002060"
_DARK = "#1a1a1a"
_MID = "#525252"
_LIGHT = "#888888"
_RULE = "#d0d7de"
_ACCENT_BG = "#f0f4f8"


def _e(s: Any) -> str:
    return _html_module.escape(str(s)) if s is not None else ""


def _na(val: Any, fallback: str = "—") -> str:
    return _e(val) if val is not None and str(val).strip() not in ("", "None") else fallback


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
  margin-bottom: 18pt;
  padding-bottom: 10pt;
  border-bottom: 2pt solid {_NAVY};
}}
.title-brand {{
  font-size: 8.5pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: {_NAVY};
}}
.title-brief {{
  font-size: 20pt;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: {_DARK};
  line-height: 1.2;
  margin-top: 6pt;
}}
.title-sub {{
  font-size: 9.5pt;
  font-weight: 300;
  color: {_MID};
  margin-top: 4pt;
}}
.title-meta {{
  font-size: 7.5pt;
  color: {_LIGHT};
  margin-top: 4pt;
  font-family: 'IBM Plex Mono', monospace;
}}

/* ── Editor's note ── */
.editors-note {{
  padding: 10pt 14pt;
  border-left: 3pt solid {_NAVY};
  background: {_ACCENT_BG};
  margin-bottom: 16pt;
}}
.editors-note-label {{
  font-size: 7pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: {_NAVY};
  margin-bottom: 4pt;
}}
.editors-note p {{
  font-size: 9.5pt;
  line-height: 1.6;
  margin: 0;
}}

/* ── KPI strip ── */
.kpi-strip {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-top: 0.5pt solid {_RULE};
  border-bottom: 0.5pt solid {_RULE};
  margin-bottom: 18pt;
}}
.kpi-cell {{
  padding: 8pt 10pt;
  border-right: 0.5pt solid {_RULE};
}}
.kpi-cell:last-child {{ border-right: none; }}
.kpi-label {{
  font-size: 7pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: {_LIGHT};
}}
.kpi-value {{
  font-size: 17pt;
  font-family: 'IBM Plex Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: {_DARK};
  margin-top: 3pt;
  line-height: 1.1;
}}
.kpi-delta {{
  font-size: 8pt;
  font-family: 'IBM Plex Mono', monospace;
  color: {_MID};
  margin-top: 2pt;
}}

/* ── Section headers ── */
h2 {{
  font-size: 8pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: {_NAVY};
  border-bottom: 0.5pt solid {_NAVY};
  padding-bottom: 3pt;
  margin: 18pt 0 9pt;
}}
h2:first-of-type {{ margin-top: 0; }}

/* ── Body text ── */
p {{
  margin: 0 0 7pt;
}}

/* ── Key facts ── */
.key-facts {{
  margin: 8pt 0 0;
}}
.key-fact {{
  padding: 5pt 8pt;
  background: #fafbfc;
  border-left: 2pt solid {_RULE};
  margin-bottom: 4pt;
  font-size: 8.5pt;
  line-height: 1.5;
}}
.key-fact-value {{
  font-family: 'IBM Plex Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: {_NAVY};
  margin-right: 4pt;
}}
.key-fact-citation {{
  font-size: 7.5pt;
  font-style: italic;
  color: {_LIGHT};
  margin-top: 2pt;
}}

/* ── Tables ── */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 7pt 0 12pt;
  font-size: 8.5pt;
}}
thead th {{
  background: {_ACCENT_BG};
  font-weight: 600;
  font-size: 7pt;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: {_MID};
  padding: 5pt 8pt;
  border-bottom: 1pt solid {_RULE};
  border-top: 1pt solid {_RULE};
  text-align: left;
}}
thead th.num {{ text-align: right; }}
tbody td {{
  padding: 4pt 8pt;
  border-bottom: 0.5pt solid {_RULE};
  vertical-align: top;
}}
tbody td.num {{
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 8pt;
}}
tbody td.label {{ font-weight: 500; }}
tbody tr:last-child td {{ border-bottom: 1pt solid {_RULE}; }}
.pos {{ color: #1a6b2d; }}
.neg {{ color: #a61c00; }}
.na  {{ color: {_LIGHT}; font-style: italic; }}

/* ── Watch list ── */
.watch-item {{
  margin: 7pt 0;
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

/* ── Print ── */
@media print {{
  h2 {{ break-after: avoid; }}
  .watch-item, .key-fact {{ break-inside: avoid; }}
  tbody tr {{ break-inside: avoid; }}
  .title-block, .editors-note {{ break-after: avoid; }}
  .kpi-strip {{ break-inside: avoid; }}
}}
"""


def _kpi_strip_html(brief_json: dict) -> str:
    kpi = brief_json.get("_kpi_strip") or {}
    macro_highlights = brief_json.get("macro_highlights") or []

    def _macro_val(indicator_contains: str) -> str:
        for m in macro_highlights:
            if indicator_contains.lower() in (m.get("indicator") or "").lower():
                return _e(m.get("value", "—"))
        return "—"

    def _macro_delta(indicator_contains: str) -> str:
        for m in macro_highlights:
            if indicator_contains.lower() in (m.get("indicator") or "").lower():
                impl = m.get("implication") or ""
                period = m.get("period") or ""
                if period:
                    return _e(period)
                return ""
        return ""

    avg_pln = kpi.get("avg_primary_pln_m2")
    avg_pln_str = f"PLN {int(avg_pln):,}" if avg_pln else "—"

    macro = brief_json.get("_macro_table") or []
    def _mt(key: str) -> str:
        for row in macro:
            if (row.get("indicator_key") or row.get("key") or "").lower() == key.lower():
                return _e(str(row.get("value", "—")))
        return "—"

    prime_yield = _mt("warsaw_prime_office_yield") or _macro_val("prime office yield")
    absorption = _mt("warsaw_office_q1_net_absorption_sqm") or _macro_val("net absorption")
    ytd_inv = _mt("warsaw_ytd_investment_volume_meur") or _macro_val("investment volume")
    if ytd_inv and ytd_inv != "—" and not ytd_inv.startswith("EUR") and not ytd_inv.startswith("M"):
        ytd_inv = f"EUR {ytd_inv}M"

    cells = [
        ("Prime Office Yield", prime_yield, ""),
        ("Q1 Net Absorption", absorption if absorption != "—" else absorption, "sqm"),
        ("Avg. Primary Price", avg_pln_str, "/m²"),
        ("YTD Investment Vol.", ytd_inv, ""),
    ]

    html = '<div class="kpi-strip">'
    for label, val, unit in cells:
        unit_html = f'<span style="font-size:8pt;font-weight:400;color:{_LIGHT};">{_e(unit)}</span>' if unit else ""
        html += f'''
<div class="kpi-cell">
  <div class="kpi-label">{_e(label)}</div>
  <div class="kpi-value">{val}{unit_html}</div>
</div>'''
    html += "</div>"
    return html


def _sections_html(sections: list[dict]) -> str:
    if not sections:
        return '<p style="color:#888;font-style:italic;">No sections available.</p>'
    out = []
    for sec in sections:
        title = sec.get("title") or sec.get("id") or "Section"
        body = sec.get("body") or ""
        key_facts = sec.get("key_facts") or []

        facts_html = ""
        if key_facts:
            facts_html = '<div class="key-facts">'
            for kf in key_facts[:6]:
                desc = kf.get("description") or ""
                val = kf.get("value") or ""
                entity = kf.get("entity") or ""
                citation = kf.get("citation") or ""
                val_html = f'<span class="key-fact-value">{_e(val)}</span>' if val else ""
                entity_html = f'<span style="font-weight:500;">{_e(entity)}</span> — ' if entity else ""
                cite_html = f'<div class="key-fact-citation">"{_e(citation)}"</div>' if citation else ""
                facts_html += f'''<div class="key-fact">
{entity_html}{val_html}{_e(desc)}
{cite_html}
</div>'''
            facts_html += "</div>"

        out.append(f'<h2>{_e(title)}</h2>\n<p>{_e(body)}</p>\n{facts_html}')
    return "\n\n".join(out)


def _price_district_table(rows: list[dict]) -> str:
    if not rows:
        return '<p style="font-size:8pt;color:#888;font-style:italic;">No residential pricing data this cycle.</p>'
    trs = ""
    for r in rows[:12]:
        district = (r.get("district") or "—").capitalize()
        units = r.get("unit_count") or "—"
        med = f"PLN {int(r['median_pln_m2']):,}" if r.get("median_pln_m2") else "—"
        rng = ""
        if r.get("min_pln_m2") and r.get("max_pln_m2"):
            rng = f"PLN {int(r['min_pln_m2']):,} – {int(r['max_pln_m2']):,}"
        trs += f"""<tr>
  <td class="label">{_e(district)}</td>
  <td class="num">{_e(str(units))}</td>
  <td class="num">{_e(med)}</td>
  <td class="num" style="color:{_LIGHT};font-size:7.5pt;">{_e(rng)}</td>
</tr>"""
    return f"""<table>
<thead><tr>
  <th>District</th>
  <th class="num">Active Units</th>
  <th class="num">Median / m²</th>
  <th class="num">Range</th>
</tr></thead>
<tbody>{trs}</tbody>
</table>"""


def _macro_table_html(macro_table: list[dict], macro_highlights: list[dict]) -> str:
    rows = macro_table or []
    # Supplement with macro_highlights if macro_table is sparse
    if not rows and macro_highlights:
        for m in macro_highlights:
            rows.append({
                "label": m.get("indicator", ""),
                "value": m.get("value", "—"),
                "period": m.get("period", ""),
                "source": "",
            })
    if not rows:
        return '<p style="font-size:8pt;color:#888;font-style:italic;">Macro indicators not populated this cycle.</p>'

    trs = ""
    for r in rows:
        label = _e(r.get("label") or r.get("indicator_key") or r.get("indicator") or "")
        val = _e(str(r.get("value", "—")))
        period = _e(r.get("period") or "")
        source = _e(r.get("source") or "")
        trs += f"""<tr>
  <td class="label">{label}</td>
  <td class="num">{val}</td>
  <td style="color:{_LIGHT};font-size:8pt;">{period}</td>
  <td style="color:{_LIGHT};font-size:7.5pt;">{source}</td>
</tr>"""
    return f"""<table>
<thead><tr>
  <th>Indicator</th>
  <th class="num">Value</th>
  <th>Period</th>
  <th>Source</th>
</tr></thead>
<tbody>{trs}</tbody>
</table>"""


def _watch_list_html(items: list[dict]) -> str:
    if not items:
        return '<p style="color:#888;font-style:italic;">No watch items.</p>'
    out = []
    for i, item in enumerate(items, 1):
        out.append(f"""<div class="watch-item">
<div class="watch-title">{i}. {_e(item.get('item', ''))}</div>
<div class="watch-trigger"><strong>Trigger:</strong> {_e(item.get('trigger', ''))}</div>
<div class="watch-timeline">{_e(item.get('timeline', ''))}</div>
</div>""")
    return "\n".join(out)


def _build_warsaw_pdf_html(brief: WeeklyBrief) -> str:
    d = brief.brief_json or {}
    week = d.get("_week_ending_long") or brief.week_ending.strftime("%-d %B %Y")
    model = d.get("_model_id", brief.model_id)
    cost = d.get("_cost_usd", float(brief.cost_usd))
    facts_total = d.get("_warsaw_facts_total", 0)

    headline = d.get("headline") or "Warsaw Weekly Market Intelligence Brief"
    subhead = d.get("subhead") or ""
    editors_note = d.get("editors_note") or ""
    sections = d.get("sections") or []
    macro_highlights = d.get("macro_highlights") or []
    watch_list = d.get("watch_list") or []
    sources_footer = d.get("sources_footer") or ""
    price_by_district = d.get("_price_by_district") or []
    macro_table = d.get("_macro_table") or []

    kpi_html = _kpi_strip_html(d)
    sections_html = _sections_html(sections)
    district_table = _price_district_table(price_by_district)
    macro_tbl = _macro_table_html(macro_table, macro_highlights)
    watch_html = _watch_list_html(watch_list)

    editors_note_html = ""
    if editors_note:
        editors_note_html = f"""<div class="editors-note">
  <div class="editors-note-label">Editor&#39;s Note</div>
  <p>{_e(editors_note)}</p>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WSRE Intelligence Warsaw — {_e(week)}</title>
<style>{_CSS}</style>
</head>
<body>

<div class="title-block">
  <div class="title-brand">WSRE Intelligence · Warsaw</div>
  <div class="title-brief">{_e(headline)}</div>
  <div class="title-sub">{_e(subhead) if subhead else f"Real estate market intelligence — Poland · Week Ending {_e(week)}"}</div>
  <div class="title-meta">Week ending {_e(week)} &nbsp;·&nbsp; {_e(model)} &nbsp;·&nbsp; ${cost:.4f} API &nbsp;·&nbsp; {facts_total} Warsaw-filtered facts</div>
</div>

{editors_note_html}

{kpi_html}

{sections_html}

<h2>Primary Residential Market — Price by District</h2>
{district_table}

<h2>Macro Indicators</h2>
{macro_tbl}

<h2>Watch List</h2>
{watch_html}

<div style="margin-top:24pt;padding-top:8pt;border-top:0.5pt solid {_RULE};font-size:7.5pt;color:{_LIGHT};">
  {_e(sources_footer) if sources_footer else "WSRE Intelligence · Warsaw · Prepared for internal circulation and select partners · Not investment advice."}
</div>

</body>
</html>"""


async def render_brief_pdf_warsaw(
    brief: WeeklyBrief,
    session: AsyncSession,
    local_path: str | None = None,
) -> str | None:
    """Render Warsaw brief to PDF.

    Uploads to blob store, updates brief.pdf_uri, and optionally saves to local_path.
    Returns blob URI string on success, None on failure.
    """
    try:
        from playwright.async_api import async_playwright

        from app.core.storage import upload_raw
    except ImportError:
        log.warning("warsaw_pdf_render_skipped", reason="playwright_not_available")
        return None

    html = _build_warsaw_pdf_html(brief)
    week = brief.week_ending.strftime("%-d %B %Y")
    week_iso = brief.week_ending.isoformat()
    cost_str = f"${float(brief.cost_usd):.4f}"

    header_tpl = (
        f'<div style="font-size:7pt;font-family:IBM Plex Sans,Helvetica,sans-serif;'
        f'width:100%;padding:0 15mm;display:flex;justify-content:space-between;color:#888;margin-top:4mm;">'
        f'<span>WSRE Intelligence · Warsaw</span>'
        f'<span>Week ending {week}</span></div>'
    )
    footer_tpl = (
        f'<div style="font-size:7pt;font-family:IBM Plex Sans,Helvetica,sans-serif;'
        f'width:100%;padding:0 15mm;display:flex;justify-content:space-between;color:#aaa;margin-bottom:4mm;">'
        f'<span>Strictly private &amp; confidential · WSRE Intelligence · '
        f'Prepared for internal circulation and select partners v0.5.0 · {week}</span>'
        f'<span><span class="pageNumber"></span> / <span class="totalPages"></span>'
        f' &nbsp;·&nbsp; {brief.model_id} &nbsp;·&nbsp; {cost_str}</span></div>'
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
        log.exception("warsaw_pdf_render_failed", week=str(brief.week_ending))
        return None

    # Save to local path if provided
    if local_path:
        import pathlib
        pathlib.Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(local_path).write_bytes(pdf_bytes)
        log.info("warsaw_pdf_saved_local", path=local_path)

    # Upload to blob store
    uri, _ = await upload_raw(
        pdf_bytes, "brief-warsaw", "pdf",
        content_type="application/pdf",
        ts=datetime.now(UTC),
    )

    brief.pdf_uri = uri
    await session.commit()

    log.info(
        "warsaw_pdf_rendered",
        week=str(brief.week_ending),
        uri=uri,
        size_kb=len(pdf_bytes) // 1024,
        local_path=local_path,
    )
    return uri
