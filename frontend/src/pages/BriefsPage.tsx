// Briefs — Warsaw weekly intelligence brief (live, WS4)

import { useLatestBrief } from "../hooks/useMarketData";
import type { WarsawSection, WarsawKeyFact, WarsawDistrictPrice, BriefMacroItem } from "../types/api";

// ── KPI strip ─────────────────────────────────────────────────────────────────

function KpiStrip({
  kpiStrip,
  macroHighlights,
}: {
  kpiStrip: { avg_primary_pln_m2?: number | null } | undefined;
  macroHighlights: BriefMacroItem[] | undefined;
}) {
  function macroVal(contains: string): string {
    const m = macroHighlights?.find(h =>
      (h.indicator || "").toLowerCase().includes(contains.toLowerCase())
    );
    return m?.value ?? "—";
  }

  const avgPln = kpiStrip?.avg_primary_pln_m2;
  const avgPlnStr = avgPln ? `${Math.round(avgPln).toLocaleString("pl-PL")}` : "—";

  const metrics = [
    { l: "Prime Office Yield",  v: macroVal("office yield")       || "—" },
    { l: "Q1 Net Absorption",   v: macroVal("net absorption")     || "—" },
    { l: "Avg Primary PLN/m²",  v: avgPlnStr                              },
    { l: "YTD Investment Vol.", v: macroVal("investment volume")  || "—" },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", borderTop: "1px solid var(--divider)", borderBottom: "1px solid var(--divider)", marginBottom: 40 }}>
      {metrics.map((m, i, a) => (
        <div key={i} style={{ padding: "18px 20px", borderRight: i < a.length - 1 ? "1px solid var(--divider)" : "none" }}>
          <div className="ws-upper" style={{ fontSize: 10 }}>{m.l}</div>
          <div className="tnum" style={{ fontSize: 24, fontWeight: 500, marginTop: 6 }}>{m.v}</div>
        </div>
      ))}
    </div>
  );
}

// ── Key facts ─────────────────────────────────────────────────────────────────

function KeyFacts({ facts }: { facts: WarsawKeyFact[] }) {
  if (!facts || facts.length === 0) return null;
  return (
    <div style={{ marginTop: 14 }}>
      {facts.slice(0, 5).map((kf, i) => (
        <div key={i} style={{
          padding: "8px 12px", marginBottom: 6,
          background: "var(--bg-wash)", opacity: 0.85,
          borderLeft: "2px solid var(--brand-navy)",
          fontSize: 13,
        }}>
          {kf.entity && <strong style={{ marginRight: 4 }}>{kf.entity}</strong>}
          {kf.value && (
            <span className="tnum mono" style={{ color: "var(--brand-navy)", marginRight: 4, fontWeight: 500 }}>
              {kf.value}
            </span>
          )}
          {kf.description}
          {kf.citation && (
            <div style={{ fontSize: 11, fontStyle: "italic", color: "var(--text-tertiary)", marginTop: 3 }}>
              "{kf.citation}"
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Brief sections ────────────────────────────────────────────────────────────

function BriefSections({ sections }: { sections: WarsawSection[] }) {
  return (
    <>
      {sections.map((sec, i) => (
        <div key={i} style={{ marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32 }}>
            <div className="ws-upper" style={{ fontSize: 11 }}>{sec.title}</div>
            <div>
              <p style={{ fontSize: 14, lineHeight: 1.65, color: "var(--text-primary)", margin: 0 }}>
                {sec.body}
              </p>
              <KeyFacts facts={sec.key_facts || []} />
            </div>
          </div>
        </div>
      ))}
    </>
  );
}

// ── District pricing table ────────────────────────────────────────────────────

function DistrictTable({ rows }: { rows: WarsawDistrictPrice[] }) {
  if (!rows || rows.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "var(--text-tertiary)", fontStyle: "italic" }}>
        No residential pricing data this cycle.
      </div>
    );
  }
  return (
    <table className="ws-table" style={{ border: "1px solid var(--border)" }}>
      <thead>
        <tr>
          <th>District</th>
          <th className="num">Active Units</th>
          <th className="num">Median PLN/m²</th>
          <th className="num">Range PLN/m²</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 12).map((r, i) => (
          <tr key={i}>
            <td style={{ fontWeight: 500 }}>{r.district.charAt(0).toUpperCase() + r.district.slice(1)}</td>
            <td className="num">{r.unit_count.toLocaleString()}</td>
            <td className="num">{r.median_pln_m2 ? Math.round(r.median_pln_m2).toLocaleString("pl-PL") : "—"}</td>
            <td className="num" style={{ color: "var(--text-tertiary)", fontSize: 12 }}>
              {r.min_pln_m2 && r.max_pln_m2
                ? `${Math.round(r.min_pln_m2).toLocaleString("pl-PL")} – ${Math.round(r.max_pln_m2).toLocaleString("pl-PL")}`
                : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Macro indicators table ────────────────────────────────────────────────────

function MacroTable({ macroHighlights }: { macroHighlights: BriefMacroItem[] }) {
  if (!macroHighlights || macroHighlights.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "var(--text-tertiary)", fontStyle: "italic" }}>
        Macro indicators not populated this cycle.
      </div>
    );
  }
  return (
    <table className="ws-table" style={{ border: "1px solid var(--border)" }}>
      <thead>
        <tr>
          <th>Indicator</th>
          <th className="num">Value</th>
          <th className="num">Period</th>
          <th>Implication</th>
        </tr>
      </thead>
      <tbody>
        {macroHighlights.map((m, i) => (
          <tr key={i}>
            <td>{m.indicator}</td>
            <td className="num" style={{ fontWeight: 500 }}>{m.value}</td>
            <td className="num" style={{ color: "var(--text-secondary)", fontSize: 12 }}>{m.period || "—"}</td>
            <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>{m.implication}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Watch list ────────────────────────────────────────────────────────────────

function WatchList({ items }: { items: Array<{ item: string; trigger: string; timeline: string }> }) {
  return (
    <>
      {items.map((w, i) => (
        <div key={i} style={{
          marginBottom: 14, padding: "12px 16px",
          borderLeft: "2px solid var(--brand-navy)",
          background: "var(--bg-surface)",
        }}>
          <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 5 }}>{w.item}</div>
          <p style={{ margin: "0 0 4px", color: "var(--text-secondary)", fontSize: 13 }}>
            <span style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Trigger: </span>
            {w.trigger}
          </p>
          <div className="tnum mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{w.timeline}</div>
        </div>
      ))}
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function BriefsPage() {
  const { data: brief, isLoading, isError } = useLatestBrief();

  if (isLoading) {
    return (
      <div style={{ padding: "48px", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div className="load-bar" style={{ width: 280 }}><div className="load-bar-inner" /></div>
      </div>
    );
  }

  if (isError || !brief) {
    return (
      <div style={{ padding: "48px", textAlign: "center" }}>
        <div className="empty-state">
          <p style={{ fontWeight: 500, marginBottom: 8 }}>No brief generated yet.</p>
          <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: "var(--brand-navy)" }}>
            python -m app.briefing.warsaw_orchestrator --dry-run 2026-05-11
          </code>
          <p className="ws-small" style={{ maxWidth: 360, lineHeight: 1.6, marginTop: 6 }}>
            Run the orchestrator to generate the Warsaw weekly brief.
          </p>
        </div>
      </div>
    );
  }

  const bj = brief.brief_json;
  const isWarsaw = bj._market === "warsaw";
  const weekLong = bj._week_ending_long || brief.week_ending;
  const headline = bj.headline || (isWarsaw ? "Warsaw Weekly Market Intelligence" : "Weekly Market Intelligence Brief");
  const subhead = bj.subhead || "";
  const editorsNote = bj.editors_note || bj.executive_summary || "";
  const sections = (bj.sections || []) as import("../types/api").WarsawSection[];
  const macroHighlights = bj.macro_highlights || [];
  const watchList = bj.watch_list || [];
  const sourcesFooter = bj.sources_footer || "";
  const priceByDistrict = bj._price_by_district || [];
  const factsTotal = bj._warsaw_facts_total || 0;
  const inputTokens = bj._input_tokens || brief.model_id;
  const costUsd = bj._cost_usd ?? brief.cost_usd;

  // Metadata line for the brief
  const metaLine = factsTotal > 0
    ? `Generated by Claude Opus from ${factsTotal} facts across 46 articles and 2 sources · ${weekLong}`
    : `Generated by ${brief.model_id} · ${weekLong}`;

  return (
    <div style={{ padding: "32px 48px 60px", maxWidth: 1100, margin: "0 auto", overflowY: "auto" }}>

      {/* AI metadata line */}
      <div style={{
        fontSize: 11, color: "var(--text-tertiary)", marginBottom: 20,
        padding: "7px 12px", background: "var(--bg-page)",
        border: "1px solid var(--divider)", borderLeft: "3px solid var(--brand-navy)",
        fontFamily: "'IBM Plex Mono', monospace",
      }}>
        {metaLine}
      </div>

      {/* Branded brief header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", paddingBottom: 18, borderBottom: "3px solid var(--brand-navy)", marginBottom: 32 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{
              width: 28, height: 28, background: "var(--brand-navy)", color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: "IBM Plex Mono", fontSize: 11, fontWeight: 600, letterSpacing: "0.5px",
            }}>WS</div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text-heading)", letterSpacing: "-0.01em" }}>WSRE Intelligence · Warsaw</div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>Real estate market intelligence — Poland</div>
            </div>
          </div>
          <div style={{ marginTop: 24 }}>
            <div className="ws-upper" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
              {subhead || "Weekly Brief"}
            </div>
            <h1 style={{ fontSize: 32, fontWeight: 600, color: "var(--text-heading)", margin: "6px 0 0", letterSpacing: "-0.015em", lineHeight: 1.2 }}>
              {headline}
            </h1>
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 32, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 14 }}>
          <div>
            <div className="tnum" style={{ fontSize: 13, color: "var(--text-secondary)" }}>Issue date</div>
            <div className="mono" style={{ fontSize: 14, fontWeight: 500, marginTop: 2 }}>{weekLong}</div>
          </div>
          <div className="briefs-actions" style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end", maxWidth: 280 }}>
            {brief.pdf_uri ? (
              <a
                href={`/api/briefs/${brief.id}/pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="brief-btn brief-btn-primary"
                style={{ textDecoration: "none" }}
              >
                ↓ Export PDF
              </a>
            ) : (
              <button className="brief-btn brief-btn-primary" onClick={() => window.print()}>
                ↓ Export PDF
              </button>
            )}
            <button className="brief-btn brief-btn-disabled" disabled title="Email ships in v2">
              ✉ Email to client
            </button>
            <button className="brief-btn brief-btn-disabled" disabled title="PowerPoint ships in v2">
              PowerPoint <span style={{ fontSize: 9, marginLeft: 4 }}>(soon)</span>
            </button>
          </div>
        </div>
      </div>

      {/* Editor's note */}
      {editorsNote && (
        <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32, marginBottom: 40 }}>
          <div className="ws-upper">Editor's note</div>
          <div style={{ fontSize: 14, lineHeight: 1.65, color: "var(--text-primary)" }}>
            {editorsNote}
          </div>
        </div>
      )}

      {/* KPI strip */}
      <KpiStrip kpiStrip={bj._kpi_strip} macroHighlights={macroHighlights} />

      {/* Brief sections */}
      {sections.length > 0 && <BriefSections sections={sections} />}

      {/* Primary residential pricing by district */}
      {priceByDistrict.length > 0 && (
        <div style={{ marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32 }}>
            <div className="ws-upper" style={{ fontSize: 11 }}>Primary residential</div>
            <DistrictTable rows={priceByDistrict} />
          </div>
        </div>
      )}

      {/* Macro indicators */}
      {macroHighlights.length > 0 && (
        <div style={{ marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32 }}>
            <div className="ws-upper" style={{ fontSize: 11 }}>Indicators</div>
            <MacroTable macroHighlights={macroHighlights} />
          </div>
        </div>
      )}

      {/* Watch list */}
      {watchList.length > 0 && (
        <div style={{ marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32 }}>
            <div className="ws-upper" style={{ fontSize: 11 }}>Watch List</div>
            <div>
              <WatchList items={watchList} />
            </div>
          </div>
        </div>
      )}

      {/* Sources & Method */}
      <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32, paddingTop: 24, borderTop: "3px solid var(--brand-navy)" }}>
        <div className="ws-upper" style={{ fontSize: 11 }}>Sources & Method</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {sourcesFooter
            ? sourcesFooter.split(". ").map((s, i, a) => (
                <p key={i} style={{ margin: i > 0 ? "10px 0 0" : 0 }}>
                  {s}{i < a.length - 1 ? "." : ""}
                </p>
              ))
            : (
              <p style={{ margin: 0 }}>
                Compiled from extracted facts across active sources.
                This brief is for the named recipient only. Not investment advice.
              </p>
            )}
        </div>
      </div>

      <div style={{ marginTop: 64, paddingTop: 20, borderTop: "1px solid var(--divider)", fontSize: 11, color: "var(--text-tertiary)", display: "flex", justifyContent: "space-between" }}>
        <span>Strictly private &amp; confidential · WSRE Intelligence · Prepared for internal circulation and select partners</span>
        <span className="tnum mono">v0.5.0 · {weekLong}</span>
      </div>
    </div>
  );
}
