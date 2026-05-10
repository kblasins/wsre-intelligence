// Briefs — Warsaw weekly intelligence brief

const briefSections = [
  {
    h: "Capital markets",
    items: [
      { t: "Allianz acquires Generation Park Y for €119m at 5.85% yield.", s: "Skanska Property Poland exit completes the Generation Park assemblage with the highest €/sqm comp on Wola at €4,920. The 24,200 sqm Q-rated tower was 94% leased on close.", src: "JLL Capital Markets · Eurobuild CEE", level: 1 },
      { t: "PFA-Norway commits €286m to Forest Tower at 5.50% — tightest Warsaw print since 2022.", s: "Single-asset transaction marks the first Norwegian sovereign deployment into Warsaw office since the 2023 pause. Spread to 10Y POLGB compressed to 32 bps.", src: "Property Forum · WSRE intercept", level: 1 },
      { t: "Cap rates: prime Centrum offer 5.65%, prime Wola 5.85%, prime Mokotów 7.20%.", s: "Centrum-vs-Mokotów spread now 155 bps, narrowest since Q4 2024 — pricing convergence on tenanted towers.", src: "Knight Frank · transacted comps", level: 2 },
    ],
  },
  {
    h: "Office leasing",
    items: [
      { t: "Net absorption Q1 2026: 58,400 sqm, +22% YoY — strongest start since pre-pandemic 2019.", s: "Wola captured 64% of net take-up; Mokotów posted negative absorption for the third consecutive quarter as 2014-vintage stock continues to repurpose.", src: "Walter Herz · Q1 Office Market View", level: 1 },
      { t: "Allegro pre-lets 15,400 sqm at Forest Tower, expanding Wola HQ campus.", s: "Brings Allegro's Warsaw footprint to 47,800 sqm. Lease commences Q1 2027 with 7-year term and CPI-linked steps.", src: "Eurobuild CEE", level: 2 },
      { t: "Citi BPO renews 24,200 sqm at V.Offices and adds 3,000 sqm.", s: "First major Mokotów retention this year — leasing team flagged as turning point for the submarket. Headline rent €17.20/sqm/mo, ~38 month free.", src: "Property Forum", level: 2 },
    ],
  },
  {
    h: "Primary residential",
    items: [
      { t: "Echo Investment posts +1.1% MoM median, leading top-12 developers.", s: "Browary Warszawskie etap VI repriced to PLN 24,800/m² (+1.64%) on 13 Apr — the highest non-Centrum primary print currently on the Jawność feed.", src: "Jawność cen mieszkań", level: 1 },
      { t: "Warsaw average primary price: PLN 16,420/m², +0.6% MoM, +9.2% YoY.", s: "79% of all 30-day price moves were increases; volume-weighted change +1.4% offsets the 142/38 increase/cut count.", src: "WSRE composite index · MRiT feed", level: 2 },
      { t: "Białołęka pipeline now 2,720 units across 2026–2028 — 28% of Warsaw total.", s: "Atal and Robyg dominate (combined 1,840 units in pipeline). Median PLN 13,400/m² remains the lowest dzielnica price.", src: "WSRE pipeline tracker", level: 2 },
    ],
  },
  {
    h: "Regulatory & political",
    items: [
      { t: "REIT-equivalent (FINN) bill enters second reading in the Sejm.", s: "If passed in the current draft, FINN vehicles will require ≥80% real-estate assets and a 90% distribution mandate. Implementation expected H1 2027.", src: "Sejm RP druk 412 · WSRE legal", level: 1 },
      { t: "NBP holds reference rate at 5.25% for the fourth consecutive month.", s: "Forward curve prices first cut for Sep 2026; office cap rates unlikely to compress materially before that move.", src: "NBP / Bankier", level: 2 },
      { t: "WSA Warsaw upholds 'Czyste-Towarowa' MPZP — 130m height ceiling stands.", s: "Settles four years of appeals from neighbouring stakeholders; unblocks four stalled Wola schemes including Towarowa 22 Phase 2.", src: "Eurobuild CEE", level: 2 },
    ],
  },
];

export function BriefsPage() {
  return (
    <div style={{ padding: "32px 48px 60px", maxWidth: 1100, margin: "0 auto", overflowY: "auto" }}>
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
            <div className="ws-upper" style={{ fontSize: 11, color: "var(--text-secondary)" }}>Weekly Brief · Vol. 14 · Issue 16</div>
            <h1 style={{ fontSize: 36, fontWeight: 600, color: "var(--text-heading)", margin: "6px 0 0", letterSpacing: "-0.015em", lineHeight: 1.15 }}>
              Norwegian capital lands in Wola; Mokotów retention turns
            </h1>
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 32, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 14 }}>
          <div>
            <div className="tnum" style={{ fontSize: 13, color: "var(--text-secondary)" }}>Issue date</div>
            <div className="mono" style={{ fontSize: 14, fontWeight: 500, marginTop: 2 }}>14 Apr 2026</div>
          </div>
          <div className="briefs-actions" style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end", maxWidth: 280 }}>
            <button className="brief-btn brief-btn-primary" onClick={() => window.print()}>
              ↓ Export PDF
            </button>
            <button className="brief-btn">✉ Email to client</button>
            <button className="brief-btn">⎘ Copy as Markdown</button>
            <button className="brief-btn brief-btn-disabled" disabled title="Slide export ships in v2">
              PowerPoint <span style={{ fontSize: 9, marginLeft: 4 }}>(soon)</span>
            </button>
          </div>
        </div>
      </div>

      {/* Editor's note */}
      <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32, marginBottom: 40 }}>
        <div className="ws-upper">Editor's note</div>
        <div style={{ fontSize: 14, lineHeight: 1.65, color: "var(--text-primary)" }}>
          Two themes this week. First, Norwegian sovereign capital is back in Warsaw — PFA's €286m write at Forest Tower prices Wola office at the tightest yield since the 2022 cycle peak. Second, after eight quarters of Mokotów weakness, Citi's V.Offices renewal-plus-expansion suggests the submarket has found a floor. We are revising our Mokotów 12-month vacancy forecast from 17.2% to 14.8%, with the caveat that 2014–2016 stock will continue to weigh on the headline number through 2027.
        </div>
      </div>

      {/* Headline numbers strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", borderTop: "1px solid var(--divider)", borderBottom: "1px solid var(--divider)", marginBottom: 40 }}>
        {[
          { l: "Prime Office Yield",  v: "5.65%",    d: "−15 bps QoQ" },
          { l: "Q1 Net Absorption",   v: "58.4k sqm",d: "+22% YoY" },
          { l: "Avg Primary PLN/m²",  v: "16,420",   d: "+0.6% MoM" },
          { l: "YTD Investment Vol.", v: "€1.04bn",  d: "+18% YoY" },
        ].map((m, i, a) => (
          <div key={i} style={{ padding: "18px 20px", borderRight: i < a.length - 1 ? "1px solid var(--divider)" : "none" }}>
            <div className="ws-upper" style={{ fontSize: 10 }}>{m.l}</div>
            <div className="tnum" style={{ fontSize: 24, fontWeight: 500, marginTop: 6 }}>{m.v}</div>
            <div className="tnum" style={{ fontSize: 11, color: "var(--up)", marginTop: 4 }}>▲ {m.d}</div>
          </div>
        ))}
      </div>

      {/* Brief sections */}
      {briefSections.map((sec, i) => (
        <div key={i} style={{ marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32 }}>
            <div>
              <div className="ws-upper" style={{ fontSize: 11 }}>{sec.h}</div>
            </div>
            <div>
              {sec.items.map((b, bi) => (
                <div key={bi} style={{ paddingBottom: 24, marginBottom: 24, borderBottom: bi < sec.items.length - 1 ? "1px solid var(--divider)" : "none" }}>
                  <h3 style={{
                    fontSize: b.level === 1 ? 18 : 15,
                    fontWeight: 600, color: "var(--text-primary)",
                    margin: 0, lineHeight: 1.35, letterSpacing: "-0.005em",
                  }}>{b.t}</h3>
                  <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text-primary)", margin: "10px 0 0" }}>{b.s}</p>
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 10, fontStyle: "italic" }}>— {b.src}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}

      {/* Indicators table */}
      <div style={{ marginBottom: 48 }}>
        <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32 }}>
          <div className="ws-upper" style={{ fontSize: 11 }}>Indicators</div>
          <div>
            <table className="ws-table" style={{ border: "1px solid var(--border)" }}>
              <thead>
                <tr>
                  <th>Indicator</th><th className="num">Latest</th><th className="num">WoW</th>
                  <th className="num">MoM</th><th className="num">YoY</th><th>Source</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["NBP Reference Rate", "5.25%", "0 bps",    "0 bps",    "−25 bps", "NBP"],
                  ["EUR/PLN",            "4.2840","+0.4%",    "+0.6%",    "−1.2%",   "NBP fixing"],
                  ["Polish 10Y",         "5.18%", "−4 bps",   "−14 bps",  "−42 bps", "Bloomberg"],
                  ["CPI YoY",            "4.6%",  "—",        "−0.2 pp",  "−1.4 pp", "GUS"],
                  ["Unemployment",       "5.1%",  "—",        "−0.1 pp",  "−0.3 pp", "GUS"],
                  ["PMI Manufacturing",  "51.4",  "+0.2",     "+0.6",     "+2.4",    "S&P Global"],
                  ["PKB YoY (latest)",   "3.2%",  "—",        "—",        "+1.0 pp", "GUS"],
                  ["Mortgage rate (5y)", "6.84%", "−6 bps",   "−18 bps",  "−84 bps", "NBP MIR"],
                ].map((r, i) => (
                  <tr key={i}>
                    <td>{r[0]}</td>
                    <td className="num">{r[1]}</td>
                    <td className="num" style={{ color: "var(--text-secondary)" }}>{r[2]}</td>
                    <td className="num" style={{ color: "var(--text-secondary)" }}>{r[3]}</td>
                    <td className="num" style={{ color: "var(--text-secondary)" }}>{r[4]}</td>
                    <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>{r[5]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Sources & Method */}
      <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 32, paddingTop: 24, borderTop: "3px solid var(--brand-navy)" }}>
        <div className="ws-upper" style={{ fontSize: 11 }}>Sources & Method</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          <p style={{ margin: 0 }}>
            Compiled from 47 underlying facts across 11 publishing sources. Capital-markets comps confirmed against ≥2 sources before publication.
            Primary residential figures sourced direct from the Jawność cen mieszkań feed (Pol. transparency law, Dz.U. 2023 poz. 1114). Sources cited per-item.
          </p>
          <p style={{ margin: "12px 0 0" }}>
            This brief is for the named recipient only. Not investment advice. Distribution outside the recipient organisation requires written consent. Confidential · WSRE Intelligence Sp. z o.o.
          </p>
        </div>
      </div>

      <div style={{ marginTop: 64, paddingTop: 20, borderTop: "1px solid var(--divider)", fontSize: 11, color: "var(--text-tertiary)", display: "flex", justifyContent: "space-between" }}>
        <span>Strictly private & confidential · WSRE Intelligence · Prepared for internal circulation and select partners</span>
        <span className="tnum mono">v0.4.2 · 14 Apr 2026</span>
      </div>
    </div>
  );
}
