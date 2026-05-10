// Commercial Market — Warsaw offices · EUR primary

import { useState } from "react";

const kpis = [
  {
    label: "Prime Office Rent", value: "€28.20", unit: "/sqm/mo",
    change: "+1.4% QoQ · +5.2% YoY", dir: "up" as const,
    spark: [24.0, 24.4, 24.8, 25.4, 26.2, 26.8, 27.4, 27.8, 28.2],
    footer: "Cushman & Wakefield · Q1 2026 · n = 38",
  },
  {
    label: "Investment Volume YTD", value: "€1.04", unit: "bn",
    change: "+18% YoY · 14 deals", dir: "up" as const,
    spark: [0.18, 0.32, 0.48, 0.62, 0.78, 0.96, 1.04],
    footer: "JLL Capital Markets · 14 Apr 2026",
  },
  {
    label: "Office Vacancy Rate", value: "9.2", unit: "%",
    change: "−40 bps QoQ", dir: "up" as const,
    spark: [11.2, 11.0, 10.6, 10.4, 10.0, 9.8, 9.6, 9.4, 9.2],
    footer: "Walter Herz · Q1 2026",
  },
  {
    label: "Prime Office Yield", value: "5.65", unit: "%",
    change: "−15 bps QoQ", dir: "up" as const,
    sub: "Centrum tower comparable",
    spark: [6.20, 6.10, 6.00, 5.95, 5.90, 5.80, 5.75, 5.70, 5.65],
    footer: "Knight Frank · transacted comps",
  },
];

const recentDeals = [
  { d: "08 Apr 2026", asset: "Generation Park Y · Wola",      buyer: "Allianz Real Estate", eur: 119.1, psm: 4920, yield: 5.85 },
  { d: "04 Apr 2026", asset: "Norblin Office · Wola",          buyer: "BNP Paribas REIM",    eur:  86.5, psm: 4600, yield: 6.05 },
  { d: "28 Mar 2026", asset: "Warsaw UNIT · Centrum",          buyer: "Deka Immobilien",     eur: 188.2, psm: 5440, yield: 5.65 },
  { d: "22 Mar 2026", asset: "Warta Tower · Centrum",          buyer: "Union Investment",    eur:  98.6, psm: 4400, yield: 6.10 },
  { d: "18 Mar 2026", asset: "Forest Tower · Wola",           buyer: "PFA-Norway",          eur: 286.7, psm: 5600, yield: 5.50 },
  { d: "14 Mar 2026", asset: "Plac Vogla · Wilanów",           buyer: "Patron Capital",      eur:  54.1, psm: 3300, yield: 6.85 },
  { d: "06 Mar 2026", asset: "Konstruktorska BC · Mokotów",    buyer: "GLP",                 eur:  92.2, psm: 2400, yield: 7.20 },
  { d: "01 Mar 2026", asset: "Empark Mokotów · Mokotów",       buyer: "PineBridge BE",       eur:  96.3, psm: 2250, yield: 7.40 },
];

const supplyPipeline = [
  { p: "Skyliner II",         dev: "Karimpol",    dist: "Wola",     gla: 58000, ph: "Under construction", eta: "Q3 2026", pre: 64 },
  { p: "Upper One",           dev: "Strabag RE",  dist: "Centrum",  gla: 36000, ph: "Under construction", eta: "Q1 2027", pre: 42 },
  { p: "The Bridge",          dev: "Ghelamco",    dist: "Wola",     gla: 47000, ph: "Topped out",         eta: "Q4 2026", pre: 55 },
  { p: "Olsen Tower",         dev: "Ghelamco",    dist: "Wola",     gla: 33000, ph: "Foundations",        eta: "Q2 2027", pre: 18 },
  { p: "Studio B",            dev: "Skanska",     dist: "Wola",     gla: 28000, ph: "Under construction", eta: "Q4 2026", pre: 71 },
  { p: "V.Offices II",        dev: "AFI Europe",  dist: "Mokotów",  gla: 21500, ph: "Planning",           eta: "Q1 2028", pre: 0  },
  { p: "Towarowa 22 Phase 2", dev: "AFI / EPP",   dist: "Wola",     gla: 64000, ph: "Permitted",          eta: "Q4 2027", pre: 12 },
  { p: "Praga Tower",         dev: "BPI RE",      dist: "Praga-Pn", gla: 24000, ph: "Permitted",          eta: "Q2 2027", pre: 0  },
];

const tenantSignals = [
  { co: "Allegro",         s: "15,400 sqm pre-let extension",          geo: "Wola · Forest Tower",    d: "11 Apr 2026", src: "Eurobuild CEE" },
  { co: "Citi BPO",        s: "24,200 sqm renewal + 3,000 sqm exp.",   geo: "Mokotów · V.Offices",    d: "08 Apr 2026", src: "Property Forum" },
  { co: "Microsoft Polska",s: "Engineering hub headcount +850 by 2027",geo: "Wola · Mennica Legacy",  d: "04 Apr 2026", src: "Money.pl" },
  { co: "Procter & Gamble",s: "22,000 sqm regional HQ relocation",     geo: "Wola · Studio",          d: "02 Apr 2026", src: "Eurobuild CEE" },
  { co: "PKO BP",          s: "Returns to office mandate · 4 days",    geo: "Centrum / Wola",         d: "28 Mar 2026", src: "Bankier" },
  { co: "Capgemini",       s: "5,400 sqm consolidation",               geo: "Mokotów → Wola Skyliner",d: "21 Mar 2026", src: "Property Forum" },
];

const regEvents = [
  { t: "REIT-equivalent (FINN) bill enters second reading", auth: "Sejm RP", d: "11 Apr 2026", impact: "Unlocks domestic institutional capital for Warsaw office. Final vote expected Q3 2026.", src: "Sejm RP · druk 412" },
  { t: "NBP holds reference rate at 5.25%",                 auth: "NBP",     d: "02 Apr 2026", impact: "Cap-rate floor on prime Warsaw office unlikely to compress further before H2 2026 cuts.", src: "Bankier" },
  { t: "UOKiK opens review of office-tenant exclusivity",   auth: "UOKiK",   d: "28 Mar 2026", impact: "Could reshape lease covenants in mixed-use Wola schemes. Comment period to 30 May.", src: "Money.pl" },
  { t: "Wola MPZP 'Czyste-Towarowa' upheld at appeal",      auth: "WSA",     d: "19 Mar 2026", impact: "Settles 130 m height ceiling on Towarowa frontage; 4 stalled schemes can proceed.", src: "Eurobuild CEE" },
];

function Spark({ data, w = 140, h = 28 }: { data: number[]; w?: number; h?: number }) {
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) =>
    `${(i * step).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`
  ).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <polyline fill="none" stroke="#002060" strokeWidth="1.4" points={pts} />
      <circle
        cx={(data.length - 1) * step}
        cy={h - (((data[data.length - 1] ?? 0) - min) / range) * h}
        r="2" fill="#002060"
      />
    </svg>
  );
}

function RentBySubmarketChart() {
  const series = [
    { name: "Centrum",     color: "#002060",  data: [24.0, 24.4, 24.8, 25.4, 26.2, 26.8, 27.4, 27.8, 28.2] },
    { name: "Wola",        color: "#2D358A",  data: [22.5, 23.0, 23.6, 24.2, 24.8, 25.4, 25.8, 26.2, 26.5] },
    { name: "Jerozolimskie",color: "#2E3192", data: [18.5, 18.8, 19.2, 19.6, 20.0, 20.4, 20.8, 21.0, 21.2] },
    { name: "Mokotów",     color: "#002060",  data: [15.8, 16.0, 16.2, 16.4, 16.5, 16.6, 16.7, 16.8, 16.8], opacity: 0.6 },
    { name: "Praga",       color: "#002060",  data: [14.0, 14.4, 15.0, 15.6, 16.4, 17.2, 18.0, 18.8, 19.4], opacity: 0.4 },
  ];
  const W = 640, H = 260, pad = { l: 40, r: 120, t: 20, b: 32 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const min = 12, max = 30;
  const x = (i: number) => pad.l + (i / 8) * iw;
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min)) * ih;
  const quarters = ["Q1-24","Q2","Q3","Q4","Q1-25","Q2","Q3","Q4","Q1-26"];
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {[12, 18, 24, 30].map(v => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#F5F5F5" />
          <text x={pad.l - 6} y={y(v) + 3} fontSize="10" fill="#525252" textAnchor="end" fontFamily="IBM Plex Sans">€{v}</text>
        </g>
      ))}
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={H - pad.b} stroke="#A3A3A3" />
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#A3A3A3" />
      {quarters.map((l, i) => (
        <text key={i} x={x(i)} y={H - pad.b + 14} fontSize="10" fill="#525252" fontFamily="IBM Plex Sans" textAnchor="middle">{l}</text>
      ))}
      {series.map((s, si) => (
        <g key={si} opacity={s.opacity || 1}>
          <polyline fill="none" stroke={s.color} strokeWidth="1.4"
            points={s.data.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
          <text x={W - pad.r + 6} y={y(s.data[s.data.length - 1] ?? 0) + 3}
            fontSize="10" fill={s.color} fontFamily="IBM Plex Sans" fontWeight="500">{s.name}</text>
        </g>
      ))}
    </svg>
  );
}

function VacancyChart() {
  const data = [
    { q: "Q1-24", overall: 11.2, centrum: 8.4,  wola: 9.6,  mokotow: 18.4 },
    { q: "Q2",    overall: 11.0, centrum: 8.0,  wola: 9.2,  mokotow: 18.0 },
    { q: "Q3",    overall: 10.6, centrum: 7.6,  wola: 8.8,  mokotow: 17.4 },
    { q: "Q4",    overall: 10.4, centrum: 7.2,  wola: 8.6,  mokotow: 17.2 },
    { q: "Q1-25", overall: 10.0, centrum: 6.8,  wola: 8.2,  mokotow: 16.8 },
    { q: "Q2",    overall:  9.8, centrum: 6.4,  wola: 7.8,  mokotow: 16.4 },
    { q: "Q3",    overall:  9.6, centrum: 6.0,  wola: 7.4,  mokotow: 16.0 },
    { q: "Q4",    overall:  9.4, centrum: 5.8,  wola: 7.0,  mokotow: 15.8 },
    { q: "Q1-26", overall:  9.2, centrum: 5.6,  wola: 6.8,  mokotow: 15.6 },
  ];
  const W = 640, H = 260, pad = { l: 40, r: 90, t: 20, b: 32 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const min = 4, max = 20;
  const x = (i: number) => pad.l + (i / 8) * iw;
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min)) * ih;
  type Row = typeof data[0];
  const series: { key: keyof Row; name: string; color: string; dash?: string }[] = [
    { key: "mokotow", name: "Mokotów",   color: "#525252" },
    { key: "overall", name: "Warsaw avg",color: "#2D358A" },
    { key: "wola",    name: "Wola",      color: "#002060" },
    { key: "centrum", name: "Centrum",   color: "#002060", dash: "3,2" },
  ];
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {[4, 8, 12, 16, 20].map(v => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#F5F5F5" />
          <text x={pad.l - 6} y={y(v) + 3} fontSize="10" fill="#525252" textAnchor="end" fontFamily="IBM Plex Sans">{v}%</text>
        </g>
      ))}
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={H - pad.b} stroke="#A3A3A3" />
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#A3A3A3" />
      {data.map((d, i) => (
        <text key={i} x={x(i)} y={H - pad.b + 14} fontSize="10" fill="#525252" fontFamily="IBM Plex Sans" textAnchor="middle">{d.q}</text>
      ))}
      {series.map(s => (
        <g key={s.key}>
          <polyline fill="none" stroke={s.color} strokeWidth="1.4"
            strokeDasharray={s.dash || ""}
            points={data.map((d, i) => `${x(i)},${y(d[s.key] as number)}`).join(" ")} />
          <text x={W - pad.r + 6} y={y((data[data.length - 1]?.[s.key] as number) ?? 0) + 3}
            fontSize="10" fill={s.color} fontFamily="IBM Plex Sans" fontWeight="500">{s.name}</text>
        </g>
      ))}
    </svg>
  );
}

export function CommercialMarketPage() {
  const [activePipeline, setActivePipeline] = useState("all");

  return (
    <div style={{ padding: "32px 48px 48px", maxWidth: 1600, margin: "0 auto", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
        <h1 className="ws-page-title">Commercial Market</h1>
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }} className="tnum">
          Last updated <span className="mono">14 Apr 2026 06:12 CEST</span> · 11 sources · 312 underlying facts
        </div>
      </div>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 32 }}>
        Warsaw commercial real estate — office rents, investment volumes, vacancy, capital markets, demand and regulation.
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 48 }}>
        {kpis.map((k, i) => (
          <div key={i} className="kpi-card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 160 }}>
            <div>
              <div className="label">{k.label}</div>
              <div className="value tnum" style={{ marginTop: 8 }}>{k.value}<span className="unit">{k.unit}</span></div>
              {k.sub && <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>{k.sub}</div>}
              <div className={"delta " + k.dir} style={{ marginTop: 8 }}>
                <span>▲</span> <span className="tnum">{k.change}</span>
              </div>
            </div>
            <Spark data={k.spark} />
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--divider)" }}>{k.footer}</div>
          </div>
        ))}
      </div>

      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Rent Trends</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 48 }}>
        <div className="ws-card">
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 10 }}>Prime asking rent by submarket — last 9 quarters</div>
          <RentBySubmarketChart />
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
            Source: Cushman & Wakefield · Walter Herz · CBRE · Knight Frank · n = 174
          </div>
        </div>
        <div className="ws-card">
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 10 }}>Vacancy rate by submarket — quarterly</div>
          <VacancyChart />
          <div style={{ fontSize: 13, color: "var(--text-primary)", marginTop: 10, padding: "10px 14px", background: "var(--bg-wash)" }}>
            Spread Centrum vs Mokotów: <span className="tnum" style={{ fontWeight: 500 }}>10.0 pp</span> — narrowest since Q3 2024
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
            Source: Walter Herz · CBRE Office Market View · Q1 2026
          </div>
        </div>
      </div>

      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Investment Volumes & Deals</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ padding: 0, marginBottom: 48 }}>
        <div style={{ padding: "16px 20px 10px" }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>Recent comparable transactions</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>8 most recent Warsaw office & mixed-use trades</div>
        </div>
        <table className="ws-table">
          <thead>
            <tr>
              <th>Date</th><th>Asset</th><th className="num">€m</th><th className="num">€/sqm</th><th className="num">Yield</th>
            </tr>
          </thead>
          <tbody>
            {recentDeals.map((r, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 12 }}>{r.d}</td>
                <td>
                  <div style={{ fontSize: 13 }}>{r.asset.split(" · ")[0]}</div>
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{r.asset.split(" · ")[1]} · {r.buyer}</div>
                </td>
                <td className="num">{r.eur.toFixed(1)}</td>
                <td className="num">{r.psm.toLocaleString()}</td>
                <td className="num">{r.yield.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Supply Pipeline</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ padding: 0, marginBottom: 48 }}>
        <div style={{ padding: "16px 20px 10px", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500 }}>Top schemes under construction or permitted</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>387,400 sqm tracked</div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {["all", "2026", "2027", "2028+"].map(f => (
              <span key={f} className={"chip" + (activePipeline === f ? " active" : "")} onClick={() => setActivePipeline(f)}>
                {f === "all" ? "All districts" : f}
              </span>
            ))}
          </div>
        </div>
        <table className="ws-table">
          <thead>
            <tr>
              <th>Project</th><th>Developer</th><th>District</th>
              <th className="num">GLA (sqm)</th><th>Phase</th><th>ETA</th><th className="num">Pre-let</th>
            </tr>
          </thead>
          <tbody>
            {supplyPipeline.map((p, i) => (
              <tr key={i}>
                <td>{p.p}</td>
                <td style={{ color: "var(--text-secondary)" }}>{p.dev}</td>
                <td style={{ color: "var(--text-secondary)" }}>{p.dist}</td>
                <td className="num">{p.gla.toLocaleString()}</td>
                <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>{p.ph}</td>
                <td className="mono" style={{ fontSize: 12 }}>{p.eta}</td>
                <td className="num" style={{ color: p.pre >= 50 ? "var(--up)" : p.pre >= 20 ? "var(--text-secondary)" : "var(--text-tertiary)" }}>
                  {p.pre}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Demand Signals</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ padding: 0, marginBottom: 48 }}>
        <div style={{ padding: "12px 16px 8px", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontSize: 12, fontWeight: 500 }}>Recent tenant signals</div>
        </div>
        <table className="ws-table">
          <thead>
            <tr><th>Date</th><th>Company</th><th>Signal</th><th>Geography</th><th>Source</th></tr>
          </thead>
          <tbody>
            {tenantSignals.map((s, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 12 }}>{s.d}</td>
                <td style={{ fontWeight: 500 }}>{s.co}</td>
                <td>{s.s}</td>
                <td style={{ color: "var(--text-secondary)" }}>{s.geo}</td>
                <td style={{ color: "var(--text-secondary)" }}>{s.src}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Regulatory Watch</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px 48px", marginBottom: 48 }}>
        {regEvents.map((r, i) => (
          <div key={i}>
            <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text-primary)", lineHeight: 1.4 }}>{r.t}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }} className="tnum">{r.auth} · <span className="mono">{r.d}</span></div>
            <div style={{ fontSize: 13, color: "var(--text-primary)", marginTop: 8, lineHeight: 1.5 }}>{r.impact}</div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>— {r.src}</div>
          </div>
        ))}
      </div>

      {/* Macro footer */}
      <div style={{ background: "#fff", border: "1px solid var(--border)", borderTop: "2px solid var(--brand-navy)", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        {[
          { l: "NBP Reference Rate", v: "5.25%" },
          { l: "EUR / PLN",          v: "4.2840" },
          { l: "Polish 10Y",         v: "5.18%" },
          { l: "CPI YoY",            v: "4.6%" },
          { l: "Unemployment",       v: "5.1%" },
          { l: "Warsaw Pop.",        v: "1.86 M" },
        ].map((m, i, a) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 24 }}>
            <div>
              <div className="ws-upper" style={{ fontSize: 10 }}>{m.l}</div>
              <div className="tnum" style={{ fontSize: 14, fontWeight: 500, marginTop: 2 }}>{m.v}</div>
            </div>
            {i < a.length - 1 && <div style={{ width: 1, height: 32, background: "var(--border)" }} />}
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 8, textAlign: "right" }}>
        Last updated <span className="mono tnum">14 Apr 2026 06:00 UTC</span> · Sources: NBP, GUS, GPW, Eurostat
      </div>

      <div style={{ marginTop: 64, paddingTop: 20, borderTop: "1px solid var(--divider)", fontSize: 11, color: "var(--text-tertiary)", display: "flex", justifyContent: "space-between" }}>
        <span>Strictly private & confidential · WSRE Intelligence · Prepared for internal circulation and select partners</span>
        <span className="tnum mono">v0.4.2 · 14 Apr 2026</span>
      </div>
    </div>
  );
}
