// Workbench V2 — three-pane: 260px saved-deals/layers | map | 480px PlotEvaluation

import { useRef, useState } from "react";
import Map, { NavigationControl, type MapRef } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

// ── Static data ────────────────────────────────────────────────────────────────

const SAVED_DEALS = [
  { id: "d1", label: "Białołęka greenfield 14ha", district: "Białołęka",  days: 2,  active: false },
  { id: "d2", label: "ul. Towarowa 28 — Wola",    district: "Wola",       days: 0,  active: true  },
  { id: "d3", label: "Mokotów Służewiec PRS",     district: "Mokotów",    days: 5,  active: false },
  { id: "d4", label: "Praga-Płd. Kamionek plot",  district: "Praga-Płd",  days: 11, active: false },
  { id: "d5", label: "Wilanów North 8ha",         district: "Wilanów",    days: 18, active: false },
];

interface LayerChild { label: string; on: boolean; }
interface LayerCat { key: string; label: string; open: boolean; children: LayerChild[]; }

const INITIAL_LAYER_TREE: LayerCat[] = [
  { key: "plots",    label: "Plots & Zoning", open: true, children: [
    { label: "Plot boundaries",        on: true  },
    { label: "MPZP coverage",          on: true  },
    { label: "MPZP function",          on: false },
    { label: "WZ decisions (24m)",     on: false },
    { label: "Conservation areas",     on: false },
  ]},
  { key: "pipeline", label: "Pipeline", open: true, children: [
    { label: "New residential (Jawność)", on: true  },
    { label: "Office under construction", on: false },
    { label: "Logistics under construction", on: false },
    { label: "Permits issued (24m)",     on: false },
  ]},
  { key: "tx",       label: "Transactions", open: false, children: [
    { label: "Land tx (24m, by PLN/m²)", on: false },
    { label: "Apartment tx heatmap",     on: false },
    { label: "Office tx (institutional)",on: false },
    { label: "Logistics tx",             on: false },
  ]},
  { key: "infra",    label: "Infrastructure", open: true, children: [
    { label: "Metro + planned extensions", on: true  },
    { label: "Tram",                       on: false },
    { label: "Major roads",                on: false },
    { label: "Schools",                    on: false },
    { label: "Hospitals",                  on: false },
    { label: "Parks",                      on: false },
  ]},
  { key: "demo",     label: "Demographics", open: false, children: [
    { label: "Population density",   on: false },
    { label: "Income heatmap",       on: false },
    { label: "Age 25-44 concentration", on: false },
  ]},
  { key: "intel",    label: "Intelligence", open: false, children: [
    { label: "News pins (7d)",    on: false },
    { label: "Regulatory events", on: false },
    { label: "Tenant signals",    on: false },
  ]},
];

// ── Plot data ─────────────────────────────────────────────────────────────────

const PLOT = {
  label: "ul. Towarowa 28 — Wola",
  kw: "WA1M/00521884/3",
  address: "ul. Towarowa 28, 01-103 Warszawa",
  area_m2: 1247,
  district: "Wola",
  fnSummary: "Residential MW (MPZP enacted) · 1,247 m² · Wola",
  mpzp: {
    name: "Czyste — Towarowa",
    enacted: "12 Mar 2026",
    fn: "MW — multi-family residential",
    far: 5.5, height: 130, coverage: 70, greenery: 25, parking: 1.2, setback: 5,
    quote: 'Plan miejscowy obszaru "Czyste — Towarowa" reaffirms 130 m max height for parcels fronting ul. Towarowa.',
    cite: "Uchwała Rady m. st. Warszawy LXXII/2356/2026, 12 Mar 2026",
  },
  landComps: {
    median: 3840, n: 14, total_m2: 38420,
    top: [
      { date: "08 Apr 2026", dist: 340,  area: 2840, pln_m2: 4120, mkt: "Primary"   },
      { date: "22 Feb 2026", dist: 520,  area: 1640, pln_m2: 3980, mkt: "Primary"   },
      { date: "14 Jan 2026", dist: 780,  area: 5210, pln_m2: 3650, mkt: "Secondary" },
      { date: "09 Nov 2025", dist: 410,  area:  980, pln_m2: 4480, mkt: "Primary"   },
      { date: "02 Sep 2025", dist: 920,  area: 3120, pln_m2: 3240, mkt: "Secondary" },
    ],
    scatter: [
      { area: 2840, pln_m2: 4120 }, { area: 1640, pln_m2: 3980 }, { area: 5210, pln_m2: 3650 },
      { area:  980, pln_m2: 4480 }, { area: 3120, pln_m2: 3240 }, { area: 1820, pln_m2: 3520 },
      { area: 2440, pln_m2: 3920 }, { area:  740, pln_m2: 4280 }, { area: 6200, pln_m2: 3140 },
      { area: 1280, pln_m2: 3680 },
    ],
  },
  apt: {
    primary_pln: 24180, primary_30d: 1.4,
    secondary_pln: 19420, secondary_12m: 9.1,
    series12m_primary:   [22600,22720,22890,23010,23150,23290,23410,23560,23720,23880,24020,24180],
    series12m_secondary: [17800,17910,18020,18180,18320,18490,18640,18790,18920,19080,19240,19420],
  },
  supply: {
    units_total: 2932, units_24m: 1428, avg_price: 23720,
    projects: [
      { dev: "Echo Investment", name: "Stacja Wola III",          dist_m:  280, units: 240, completion: "Q4 2026", pln: 21900, sold: 142, vel: 8.0 },
      { dev: "Develia",         name: "Wola Libero",              dist_m:  640, units: 268, completion: "Q2 2027", pln: 24650, sold:  94, vel: 6.2 },
      { dev: "Marvipol",        name: "Unisono Wola",             dist_m:  880, units: 412, completion: "Q1 2027", pln: 22900, sold: 286, vel:11.4 },
      { dev: "Skanska Resi.",   name: "Holm House III",           dist_m: 1080, units: 184, completion: "Q3 2026", pln: 25400, sold: 148, vel: 9.2 },
      { dev: "Atal",            name: "Atal Towarowa",            dist_m: 1320, units: 520, completion: "Q4 2027", pln: 22150, sold: 128, vel: 5.8 },
      { dev: "Robyg",           name: "Wola Skyline",             dist_m: 1540, units: 308, completion: "Q1 2028", pln: 23280, sold:  42, vel: 4.4 },
      { dev: "Dom Development", name: "Browary 12",               dist_m: 1720, units: 240, completion: "Q3 2027", pln: 25180, sold:  86, vel: 7.1 },
      { dev: "Spravia",         name: "Apartamenty Kasprzaka",    dist_m: 1880, units: 760, completion: "Q2 2028", pln: 22640, sold:  38, vel: 3.8 },
    ],
  },
  demo: {
    pop: 140820, pop_5y: 4.2, pop_series: [135150,136420,137620,138940,140820],
    age_25_44_pct: 38.6, warsaw_avg: 32.1,
    income: 9420, income_3y: 18.4, income_warsaw: 8740, income_series: [7960,8240,8590,8910,9420],
    dwellings_per_1000: 472, dwellings_warsaw: 514,
  },
  infra: {
    metro: { name: "M2 · Płocka", dist_m: 340 },
    tram: { name: "23 / 24 / 28", dist_m: 120 },
    planned: [
      { prj: "M3 line — Wola spur",              status: "Funded",          eta: "2031",    src: "MZA"     },
      { prj: "S8 / Towarowa interchange upgrade", status: "In construction", eta: "Q4 2026", src: "GDDKiA"  },
    ],
    schools: 6, hospitals: 3,
  },
  intel: [
    { ts: "08 Apr 26", t: "transaction", txt: "Allianz Real Estate completes Generation Park Y · €119m at 5.85% yield.",               src: "Eurobuild CEE",         conf: 5 },
    { ts: "28 Mar 26", t: "listing",     txt: "Echo Investment opens sales for Stacja Wola III — guide PLN 23,900/m².",                src: "Property Forum",        conf: 5 },
    { ts: "22 Mar 26", t: "regulatory",  txt: "WSA Warsaw upholds 'Czyste-Towarowa' MPZP — 130m ceiling final.",                       src: "Rzeczpospolita · NRC",  conf: 5 },
    { ts: "14 Mar 26", t: "sentiment",   txt: "Marvipol reports 286 of 412 units sold at Unisono Wola (69% absorption).",              src: "Bankier",               conf: 4 },
    { ts: "06 Mar 26", t: "macro",       txt: "NBP holds reference rate at 5.25% for fourth consecutive meeting.",                      src: "NBP",                   conf: 5 },
  ],
};

const PLOT_B = {
  label: "Białołęka greenfield · 14 ha",
  kw: "WA1B/00128710/4",
  address: "ul. Modlińska / Płochocińska, Białołęka",
  area_m2: 140000, district: "Białołęka",
  fnSummary: "MN/MW (WZ pending) · 14.0 ha · Białołęka",
  mpzp: { name: "None — WZ in process", fn: "MN / MW residential", far: 1.4, height: 18, status: "warn" as const },
  landMedian: 1840, landN: 8,
  apt: { primary: 13400, yoy: 5.8 },
  supplyUnits: 2720, supplyDist: 1.8,
  demo: { pop: 139000, pop_5y: 12.4, age2544: 31.2, income: 8420 },
  metro: "M3 (planned, ETA 2031)", metroDist: 1400,
  signal: "Long-dated greenfield. Pricing 5× cheaper than Wola plot but no MPZP and weaker exit price.",
};

const PLOT_A_LITE = {
  label: "ul. Towarowa 28 — Wola",
  kw: "WA1M/00521884/3",
  address: "ul. Towarowa 28, 01-103 Warszawa",
  area_m2: 1247, district: "Wola",
  fnSummary: "MW (MPZP enacted) · 1,247 m² · Wola",
  mpzp: { name: "Czyste — Towarowa", fn: "MW", far: 5.5, height: 130, status: "ok" as const },
  landMedian: 3840, landN: 14,
  apt: { primary: 24180, yoy: 14.8 },
  supplyUnits: 2840, supplyDist: 2.0,
  demo: { pop: 140820, pop_5y: 4.2, age2544: 38.6, income: 9420 },
  metro: "M2 · Płocka", metroDist: 340,
  signal: "Short-cycle infill. Premium PUM, fully entitled, but priced in.",
};

// ── Mini chart helpers ─────────────────────────────────────────────────────────

function SparkLine({ data, color = "var(--brand-navy)", w = 70, h = 18 }: { data: number[]; color?: string; w?: number; h?: number }) {
  const mn = Math.min(...data), mx = Math.max(...data), r = mx - mn || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / r) * h}`).join(" ");
  return (
    <svg width={w} height={h} style={{ display: "inline-block", verticalAlign: "middle", marginLeft: 6 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" />
    </svg>
  );
}

function DualLine({ a, b, h = 70 }: { a: number[]; b: number[]; h?: number }) {
  const W = 420;
  const all = [...a, ...b]; const mn = Math.min(...all), mx = Math.max(...all); const r = mx - mn || 1;
  const ptsA = a.map((v, i) => `${(i / (a.length - 1)) * W},${h - ((v - mn) / r) * h}`).join(" ");
  const ptsB = b.map((v, i) => `${(i / (b.length - 1)) * W},${h - ((v - mn) / r) * h}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${h}`} preserveAspectRatio="none" width="100%" height={h} style={{ display: "block" }}>
      <polyline points={ptsA} fill="none" stroke="var(--brand-navy)" strokeWidth="1.5" />
      <polyline points={ptsB} fill="none" stroke="var(--brand-blue-2)" strokeWidth="1.5" strokeDasharray="3 2" />
    </svg>
  );
}

function CompsScatter() {
  const W = 420, H = 120, pad = 22;
  const data = PLOT.landComps.scatter;
  const minP = 2800, maxP = 4800;
  const x = (i: number) => pad + (i / (data.length - 1)) * (W - pad * 2);
  const y = (v: number) => H - pad - ((v - minP) / (maxP - minP)) * (H - pad * 2);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      {[3000, 3500, 4000, 4500].map(v => (
        <g key={v}>
          <line x1={pad} x2={W - pad} y1={y(v)} y2={y(v)} stroke="#F0F0F0" />
          <text x={2} y={y(v) + 3} fontSize="9" fill="var(--text-tertiary)" fontFamily="IBM Plex Mono">{(v / 1000).toFixed(1)}k</text>
        </g>
      ))}
      <line x1={pad} x2={W - pad} y1={y(PLOT.landComps.median)} y2={y(PLOT.landComps.median)} stroke="var(--brand-navy)" strokeWidth="1" strokeDasharray="2 2" />
      <text x={W - pad - 1} y={y(PLOT.landComps.median) - 3} fontSize="9" fill="var(--brand-navy)" textAnchor="end">median 3.84k</text>
      {data.map((d, i) => (
        <circle key={i} cx={x(i)} cy={y(d.pln_m2)} r={Math.sqrt(d.area) / 12}
          fill="var(--brand-navy)" fillOpacity="0.35" stroke="var(--brand-navy)" strokeWidth="0.6" />
      ))}
    </svg>
  );
}

// ── KV component ──────────────────────────────────────────────────────────────

function KV({ rows }: { rows: [string, React.ReactNode, string?][] }) {
  return (
    <div className="kv">
      {rows.map(([k, v, cls], i) => (
        <>
          <div key={"k" + i} className="k">{k}</div>
          <div key={"v" + i} className={"v " + (cls ?? "")}>{v}</div>
        </>
      ))}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHd({ letter, title, subtitle }: { letter: string; title: string; subtitle?: string }) {
  return (
    <div className="pe-hd">
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)", letterSpacing: "0.5px" }}>{letter}</span>
        <span className="ws-upper">{title}</span>
      </div>
      {subtitle && <div className="pe-sub">{subtitle}</div>}
    </div>
  );
}

// ── Conf dots ─────────────────────────────────────────────────────────────────

function ConfDots({ n }: { n: number }) {
  return (
    <span style={{ display: "inline-flex", gap: 2, verticalAlign: "middle" }}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: i <= n ? "var(--brand-navy)" : "var(--border)" }} />
      ))}
    </span>
  );
}

// ── Underwriting (Section I) ──────────────────────────────────────────────────

function Underwriting() {
  const [buildCost] = useState(5500);
  const [irr] = useState(18);
  const [ltv] = useState(65);
  const [growth] = useState(3);
  const [duration] = useState(24);

  const area = PLOT.area_m2;
  const far = PLOT.mpzp.far;
  const pum = area * far;
  const exit = PLOT.apt.primary_pln * Math.pow(1 + growth / 100, 2);
  const gdv = pum * exit / 1_000_000;
  const cost_build = pum * buildCost / 1_000_000;
  const cost_soft = cost_build * 0.15;
  const debt = (cost_build + cost_soft) * (ltv / 100);
  const finCost = debt * 0.0835 * 1.5;
  const totalCost = cost_build + cost_soft + finCost;
  const targetMargin = 1 + irr / 100;
  const residual = Math.max(0, gdv - totalCost * targetMargin);
  const residual_pln_m2 = residual * 1_000_000 / area;

  const fmtM = (v: number) => v.toLocaleString("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const fmtInt = (v: number) => Math.round(v).toLocaleString("pl-PL");

  function corner(pd: number, cd: number) {
    const g = pum * exit * (1 + pd) / 1_000_000;
    const c = (cost_build + cost_soft) * (1 + cd) + finCost;
    const r = g - c * targetMargin;
    return r > 0 ? r * 1_000_000 / area : 0;
  }
  const c_HP_LC = corner(+0.05, -0.10);
  const c_HP_HC = corner(+0.05, +0.10);
  const c_LP_LC = corner(-0.05, -0.10);
  const c_LP_HC = corner(-0.05, +0.10);

  function SensCell({ v, tone }: { v: number; tone?: "good" | "bad" }) {
    const bg = tone === "good" ? "#ECF2EC" : tone === "bad" ? "#F2ECEC" : "#FAFAFA";
    const c = tone === "good" ? "var(--up)" : tone === "bad" ? "var(--down)" : "var(--text-primary)";
    return (
      <div style={{ background: bg, color: c, padding: "10px 12px", border: "1px solid var(--border)" }}>
        <div style={{ fontSize: 14, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>{fmtInt(v)}</div>
      </div>
    );
  }

  function InputRow({ label, sub, value }: { label: string; sub?: string; value: string | number }) {
    return (
      <div className="pe-uw-input-row">
        <div className="pe-uw-input-l">
          <div className="l1">{label}</div>
          {sub && <div className="l2">{sub}</div>}
        </div>
        <div className="pe-uw-input-v tnum">
          <span>{value}</span>
          <span className="pe-uw-pencil" aria-hidden="true">✎</span>
        </div>
      </div>
    );
  }

  return (
    <div className="pe-section pe-uw">
      <SectionHd letter="I" title="Underwriting Snapshot" subtitle="Screening only · not full underwrite" />
      <div className="pe-uw-grid">
        <div className="pe-uw-out">
          <div className="pe-uw-out-block">
            <div className="pe-uw-out-label">Estimated GDV</div>
            <div className="pe-uw-out-gdv tnum">PLN {fmtM(gdv)}M</div>
          </div>
          <div className="pe-uw-out-block" style={{ marginTop: 10 }}>
            <div className="pe-uw-out-label">Estimated total cost</div>
            <div className="pe-uw-out-cost tnum">PLN {fmtM(totalCost)}M</div>
          </div>
          <div className="pe-uw-rule" />
          <div className="pe-uw-out-label">Max land price at target IRR</div>
          <div className="pe-uw-residual tnum">
            PLN {fmtInt(residual_pln_m2)}
            <span className="pe-uw-residual-unit">/m²</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
            Total: PLN {fmtM(residual)}M for {area.toLocaleString("pl-PL")} m² plot
          </div>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", margin: "18px 0 6px" }}>
            Sensitivity (±5% price × ±10% cost)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            <SensCell v={c_HP_LC} tone="good" />
            <SensCell v={c_HP_HC} />
            <SensCell v={c_LP_LC} />
            <SensCell v={c_LP_HC} tone="bad" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 4, fontSize: 10, color: "var(--text-tertiary)" }}>
            <div>+price / −cost</div>
            <div style={{ textAlign: "right" }}>+price / +cost</div>
            <div>−price / −cost</div>
            <div style={{ textAlign: "right" }}>−price / +cost</div>
          </div>
        </div>
        <div className="pe-uw-divider" />
        <div className="pe-uw-in">
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Inputs</div>
          <InputRow label="Build cost"     sub="PLN/m² PUM"        value={fmtInt(buildCost)} />
          <InputRow label="Target IRR"     sub="%"                 value={irr} />
          <InputRow label="Financing"      sub="% LTV · WIBOR+2.5" value={`${ltv}%`} />
          <InputRow label="Sales velocity" sub="units / mo"        value="6" />
          <InputRow label="Build duration" sub="months"            value={duration} />
        </div>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-tertiary)", lineHeight: 1.5, marginTop: 18 }}>
        This is a screening tool. Always run a full underwrite before committing capital.
      </div>
    </div>
  );
}

// ── PlotEvaluation panel ──────────────────────────────────────────────────────

function PlotEvaluation() {
  const [saved, setSaved] = useState(true);

  const ratio = PLOT.demo.dwellings_per_1000 / PLOT.demo.dwellings_warsaw;
  const supply = ratio < 0.95
    ? { label: "under-supplied", color: "var(--up)", bg: "#ECF2EC" }
    : ratio < 1.05
    ? { label: "balanced", color: "var(--warn)", bg: "#F2EFE6" }
    : { label: "over-supplied", color: "var(--down)", bg: "#F2ECEC" };

  return (
    <aside className="eval-panel" style={{ width: 480 }}>
      {/* Plot identifier strip */}
      <div className="pe-id-strip">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Plot Evaluation · Wola</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-heading)", marginTop: 4 }}>{PLOT.label}</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3, fontFamily: "IBM Plex Mono" }}>KW {PLOT.kw}</div>
          </div>
          <button className={"pe-star " + (saved ? "on" : "")} onClick={() => setSaved(!saved)} title="Save deal">★</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 10 }}>{PLOT.address}</div>
        <div style={{ fontSize: 12, color: "var(--text-primary)", marginTop: 4 }}>
          <span className="tnum">{PLOT.area_m2.toLocaleString("pl-PL")}</span> m² · {PLOT.fnSummary}
        </div>
        <div className="pe-actions">
          <button className="pe-btn pe-btn-primary">Generate Plot Report (PDF)</button>
          <button className="pe-btn">Compare</button>
          <button className="pe-btn">Track</button>
        </div>
      </div>

      {/* A — Zoning */}
      <div className="pe-section">
        <SectionHd letter="A" title="Zoning & Planning" />
        <div className="pe-status pe-status-ok">
          <span className="dot" /> MPZP enacted · {PLOT.mpzp.name} · {PLOT.mpzp.enacted}
        </div>
        <KV rows={[
          ["Function code",     PLOT.mpzp.fn],
          ["Max FAR",           <span className="tnum">{PLOT.mpzp.far}</span>],
          ["Max height",        <span><span className="tnum">{PLOT.mpzp.height}</span> m</span>],
          ["Max site coverage", <span><span className="tnum">{PLOT.mpzp.coverage}</span>%</span>],
          ["Min greenery",      <span><span className="tnum">{PLOT.mpzp.greenery}</span>%</span>],
          ["Min parking ratio", <span><span className="tnum">{PLOT.mpzp.parking}</span> per unit</span>],
          ["Front setback",     <span><span className="tnum">{PLOT.mpzp.setback}</span> m</span>],
        ]} />
        <div className="source-quote">
          {PLOT.mpzp.quote}
          <span className="source-attr">— {PLOT.mpzp.cite}</span>
        </div>
        <a className="how-link" href="#">View MPZP text · PL ↔ EN</a>
      </div>

      {/* B — Land Comps */}
      <div className="pe-section">
        <SectionHd letter="B" title="Land comparable transactions" subtitle="Last 24 months · 1 km radius · RCN" />
        <div className="pe-stat-row">
          <div className="stat"><div className="v tnum">3,840</div><div className="l">PLN/m² median</div></div>
          <div className="stat"><div className="v tnum">{PLOT.landComps.n}</div><div className="l">comparable tx</div></div>
          <div className="stat"><div className="v tnum">{(PLOT.landComps.total_m2 / 1000).toFixed(1)}k</div><div className="l">m² traded</div></div>
        </div>
        <div style={{ marginTop: 12, marginBottom: 8 }}><CompsScatter /></div>
        <table className="pe-table">
          <thead>
            <tr><th>Date</th><th className="num">Dist</th><th className="num">Area</th><th className="num">PLN/m²</th><th>Mkt</th></tr>
          </thead>
          <tbody>
            {PLOT.landComps.top.map((c, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 11 }}>{c.date}</td>
                <td className="num"><span className="tnum">{c.dist}</span> m</td>
                <td className="num tnum">{c.area.toLocaleString("pl-PL")}</td>
                <td className="num tnum"><strong>{c.pln_m2.toLocaleString("pl-PL")}</strong></td>
                <td style={{ fontSize: 11, color: "var(--text-secondary)" }}>{c.mkt}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <a className="how-link" href="#">How comps are selected</a>
      </div>

      {/* C — Apartment Exit */}
      <div className="pe-section">
        <SectionHd letter="C" title="Apartment exit pricing" subtitle="1 km radius · Jawność cen + RCN" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div className="pe-mini-card">
            <div className="t">Primary market</div>
            <div className="v tnum">{PLOT.apt.primary_pln.toLocaleString("pl-PL")} <span className="u">PLN/m²</span></div>
            <div className="d" style={{ color: "var(--up)" }}>+{PLOT.apt.primary_30d}% · 30d</div>
          </div>
          <div className="pe-mini-card">
            <div className="t">Secondary market</div>
            <div className="v tnum">{PLOT.apt.secondary_pln.toLocaleString("pl-PL")} <span className="u">PLN/m²</span></div>
            <div className="d" style={{ color: "var(--up)" }}>+{PLOT.apt.secondary_12m}% · 12m</div>
          </div>
        </div>
        <DualLine a={PLOT.apt.series12m_primary} b={PLOT.apt.series12m_secondary} />
        <div style={{ display: "flex", gap: 14, marginTop: 6, fontSize: 11, color: "var(--text-secondary)" }}>
          <span><span style={{ display: "inline-block", width: 14, height: 2, background: "var(--brand-navy)", verticalAlign: "middle", marginRight: 4 }} />Primary</span>
          <span><span style={{ display: "inline-block", width: 14, height: 2, background: "var(--brand-blue-2)", verticalAlign: "middle", marginRight: 4 }} />Secondary</span>
        </div>
        <div style={{ marginTop: 14, padding: "12px 14px", background: "var(--bg-wash)", border: "1px solid var(--border)" }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Projected exit · 24 months · @ 3% / yr</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <div><div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Conservative</div><div className="tnum" style={{ fontSize: 14, fontWeight: 500 }}>24,900</div></div>
            <div><div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Central</div><div className="tnum" style={{ fontSize: 14, fontWeight: 500, color: "var(--brand-navy)" }}>25,650</div></div>
            <div><div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Optimistic</div><div className="tnum" style={{ fontSize: 14, fontWeight: 500 }}>26,420</div></div>
          </div>
        </div>
      </div>

      {/* D — Competing Supply */}
      <div className="pe-section">
        <SectionHd letter="D" title="Competing residential supply" subtitle="2 km radius · pipeline + permitted" />
        <div className="pe-stat-row">
          <div className="stat"><div className="v tnum">{PLOT.supply.units_total.toLocaleString("pl-PL")}</div><div className="l">units in pipeline</div></div>
          <div className="stat"><div className="v tnum">{PLOT.supply.units_24m.toLocaleString("pl-PL")}</div><div className="l">deliver ≤24 m</div></div>
          <div className="stat"><div className="v tnum">{PLOT.supply.avg_price.toLocaleString("pl-PL")}</div><div className="l">avg PLN/m²</div></div>
        </div>
        <table className="pe-table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ minWidth: 96 }}>Developer</th><th>Project</th>
              <th className="num">Dist</th><th className="num">Units</th>
              <th>Compl.</th><th className="num">PLN/m²</th>
              <th className="num">Sold</th><th className="num">/mo</th>
            </tr>
          </thead>
          <tbody>
            {PLOT.supply.projects.map((p, i) => (
              <tr key={i}>
                <td style={{ fontSize: 12, fontWeight: 500 }}>{p.dev}</td>
                <td style={{ fontSize: 11, color: "var(--text-secondary)" }}>{p.name}</td>
                <td className="num tnum">{p.dist_m} m</td>
                <td className="num tnum">{p.units}</td>
                <td className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>{p.completion}</td>
                <td className="num tnum"><strong>{p.pln.toLocaleString("pl-PL")}</strong></td>
                <td className="num tnum">{p.sold}</td>
                <td className="num tnum">{p.vel.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <a className="how-link" href="#" style={{ marginTop: 6, display: "inline-block" }}>View all on map</a>
      </div>

      {/* E — Demographics */}
      <div className="pe-section">
        <SectionHd letter="E" title="Demographics & macro" subtitle="Wola · gmina + dzielnica" />
        <div className="kv">
          <div className="k">Population</div>
          <div className="v">
            <span className="tnum">{PLOT.demo.pop.toLocaleString("pl-PL")}</span>
            <SparkLine data={PLOT.demo.pop_series} />
            <span style={{ display: "block", fontSize: 10, color: "var(--up)", marginTop: 1 }}>+{PLOT.demo.pop_5y}% · 5y</span>
          </div>
          <div className="k">Age 25–44</div>
          <div className="v">
            <span className="tnum">{PLOT.demo.age_25_44_pct}%</span>
            <span style={{ display: "block", fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>vs Warsaw {PLOT.demo.warsaw_avg}%</span>
          </div>
          <div className="k">Avg gross / mo</div>
          <div className="v">
            PLN <span className="tnum">{PLOT.demo.income.toLocaleString("pl-PL")}</span>
            <SparkLine data={PLOT.demo.income_series} />
            <span style={{ display: "block", fontSize: 10, color: "var(--up)", marginTop: 1 }}>+{PLOT.demo.income_3y}% · 3y</span>
          </div>
          <div className="k">Dwellings / 1,000</div>
          <div className="v">
            <span className="tnum">{PLOT.demo.dwellings_per_1000}</span>
            <span style={{ display: "inline-block", marginLeft: 8, padding: "2px 6px", fontSize: 10, fontWeight: 500, background: supply.bg, color: supply.color, textTransform: "uppercase", letterSpacing: "0.3px", verticalAlign: "middle" }}>{supply.label}</span>
            <span style={{ display: "block", fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>Warsaw {PLOT.demo.dwellings_warsaw}</span>
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 14 }}>GUS BDL · 2025 Q4</div>
      </div>

      {/* F — Infrastructure */}
      <div className="pe-section">
        <SectionHd letter="F" title="Infrastructure" subtitle="Distance to amenities" />
        <div className="kv">
          <div className="k">Nearest metro</div>
          <div className="v">Rondo Daszyńskiego · M2 · <span className="tnum">4</span> min</div>
          <div className="k">Nearest tram</div>
          <div className="v">{PLOT.infra.tram.name} · <span className="tnum">{PLOT.infra.tram.dist_m}</span> m</div>
          <div className="k">Schools (1 km)</div>
          <div className="v tnum">{PLOT.infra.schools}</div>
          <div className="k">Healthcare (2 km)</div>
          <div className="v tnum">{PLOT.infra.hospitals}</div>
        </div>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", margin: "16px 0 0" }}>Planned transport · 5 km</div>
        {PLOT.infra.planned.map((p, i) => {
          const st = p.status === "Funded"
            ? { bg: "var(--bg-wash)", c: "var(--brand-navy)" }
            : p.status === "In construction"
            ? { bg: "#ECF2EC", c: "var(--up)" }
            : { bg: "#F2EFE6", c: "var(--warn)" };
          return (
            <div key={i} style={{ padding: "9px 0", borderTop: "1px solid var(--divider)", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, gap: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12 }}>{p.prj}</div>
                <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 1 }}>{p.src} · ETA {p.eta}</div>
              </div>
              <span style={{ fontSize: 10, padding: "2px 6px", background: st.bg, color: st.c, textTransform: "uppercase", fontWeight: 500, letterSpacing: "0.3px" }}>{p.status}</span>
            </div>
          );
        })}
      </div>

      {/* G — Regulatory */}
      <div className="pe-section">
        <SectionHd letter="G" title="Regulatory & political" subtitle="Risk indicators · Wola" />
        {[
          { date: "02 Mar 26", cat: "Council",       t: "Resolution LXXII/2356/2026 — MPZP Czyste-Towarowa enacted (low risk)." },
          { date: "14 Jan 26", cat: "Council",       t: "Motion to review Wola green-cover ratios — referred to committee, no draft yet." },
          { date: "—",         cat: "Environmental", t: "No Natura 2000 within plot. Closest: Łęgi Czerniakowskie 4.2 km. Heritage zone informational only." },
          { date: "21 May 26", cat: "Consultation",  t: "Public consultation — Wola corridor parking strategy. Window closes 21 May 2026." },
        ].map((it, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "68px 1fr 14px", gap: 10, padding: "10px 0", borderTop: i ? "1px solid var(--divider)" : "none", alignItems: "flex-start" }}>
            <div>
              <div className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{it.date}</div>
              <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.3px", marginTop: 2 }}>{it.cat}</div>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-primary)", lineHeight: 1.4 }}>{it.t}</div>
            <a href="#" style={{ fontSize: 11, color: "var(--text-tertiary)", textAlign: "right" }}>↗</a>
          </div>
        ))}
      </div>

      {/* H — Recent Intelligence */}
      <div className="pe-section">
        <SectionHd letter="H" title="Recent intelligence" subtitle="Last 30 days · Wola + residential primary" />
        {PLOT.intel.map((it, i) => (
          <div key={i} style={{ padding: "11px 0", borderTop: i ? "1px solid var(--divider)" : "none" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{it.ts}</span>
              <span className={"type-pill " + it.t} style={{ fontSize: 9 }}>{it.t}</span>
              <span style={{ marginLeft: "auto" }}><ConfDots n={it.conf} /></span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-primary)", lineHeight: 1.45 }}>{it.txt}</div>
            <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 3 }}>{it.src}</div>
          </div>
        ))}
      </div>

      {/* I — Underwriting */}
      <Underwriting />

      {/* Footer */}
      <div className="pe-footer">
        <button className="pe-btn pe-btn-primary pe-btn-lg">Generate Plot Report (PDF)</button>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 6, textAlign: "center" }}>
          4–6 page report · PL + EN sections · ~15s generation
        </div>
        <button className="pe-btn pe-btn-disabled" style={{ width: "100%", marginTop: 10 }} disabled>
          Export to PowerPoint <span style={{ fontSize: 10, color: "var(--text-tertiary)", marginLeft: 6 }}>(coming soon)</span>
        </button>
      </div>
    </aside>
  );
}

// ── PlotCompareView ───────────────────────────────────────────────────────────

function PlotCol({ p, isA }: { p: typeof PLOT_A_LITE | typeof PLOT_B; isA: boolean }) {
  const fmtN = (v: number) => v.toLocaleString("pl-PL");
  return (
    <div style={{ flex: 1, padding: "18px 20px", borderRight: isA ? "1px solid var(--border)" : "none", minWidth: 0, overflowY: "auto" }}>
      <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{isA ? "Plot A" : "Plot B"}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-heading)", marginTop: 4, lineHeight: 1.3 }}>{p.label}</div>
      <div className="mono" style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 3 }}>KW {p.kw}</div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.4 }}>{p.address}</div>
      <div style={{ fontSize: 11, color: "var(--text-primary)", marginTop: 4 }}>
        <span className="tnum">{fmtN(p.area_m2)}</span> m² · {p.district}
      </div>

      <div style={{ marginTop: 14, padding: "8px 10px", background: p.mpzp.status === "ok" ? "#ECF2EC" : "#FFF8E1", border: "1px solid " + (p.mpzp.status === "ok" ? "rgba(31,107,58,0.2)" : "rgba(180,138,0,0.2)"), fontSize: 11, lineHeight: 1.4 }}>
        <div style={{ fontWeight: 500, color: p.mpzp.status === "ok" ? "var(--up)" : "#8B6914" }}>
          {p.mpzp.status === "ok" ? "● MPZP enacted" : "▲ No MPZP"}
        </div>
        <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>{p.mpzp.name}</div>
        <div style={{ color: "var(--text-primary)", marginTop: 4 }}>
          FAR <span className="tnum">{p.mpzp.far}</span> · H <span className="tnum">{p.mpzp.height}</span>m · {p.mpzp.fn}
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Land comp</div>
        <div className="tnum" style={{ fontSize: 18, fontWeight: 500 }}>{fmtN(p.landMedian)} <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 400 }}>PLN/m²</span></div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>median · {p.landN} comps · 1 km</div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Apt exit (primary)</div>
        <div className="tnum" style={{ fontSize: 18, fontWeight: 500 }}>{fmtN(p.apt.primary)} <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 400 }}>PLN/m²</span></div>
        <div style={{ fontSize: 11, color: "var(--up)" }}>+{p.apt.yoy.toFixed(1)}% YoY</div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Competing supply</div>
        <div className="tnum" style={{ fontSize: 14, fontWeight: 500 }}>{fmtN(p.supplyUnits)} units</div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>within {p.supplyDist} km</div>
      </div>

      <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--divider)" }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Demographics</div>
        <div style={{ fontSize: 11, lineHeight: 1.6, color: "var(--text-primary)" }}>
          Pop <span className="tnum">{fmtN(p.demo.pop)}</span> · <span style={{ color: "var(--up)" }}>+{p.demo.pop_5y}% 5y</span><br />
          Age 25–44 <span className="tnum">{p.demo.age2544}%</span><br />
          Avg inc PLN <span className="tnum">{fmtN(p.demo.income)}</span>/mo
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Transit</div>
        <div style={{ fontSize: 11, color: "var(--text-primary)" }}>{p.metro}</div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{fmtN(p.metroDist)} m walk</div>
      </div>

      <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--bg-wash)", fontSize: 11, lineHeight: 1.5, color: "var(--text-primary)" }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 4 }}>Signal</div>
        {p.signal}
      </div>
    </div>
  );
}

function PlotCompareView() {
  return (
    <aside className="eval-panel" style={{ width: 560, display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", background: "#fff", display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
        <div>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Compare mode</div>
          <div style={{ fontSize: 13, fontWeight: 500, marginTop: 2 }}>Towarowa 28 vs. Białołęka greenfield</div>
        </div>
        <button className="pe-btn pe-btn-primary" style={{ fontSize: 11, padding: "6px 10px" }}>
          Generate comparison PDF
        </button>
      </div>
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <PlotCol p={PLOT_A_LITE} isA={true} />
        <PlotCol p={PLOT_B} isA={false} />
      </div>
      <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--text-tertiary)", background: "#FAFAFA", lineHeight: 1.5, flexShrink: 0 }}>
        Toggle Compare off to return to single-plot Evaluation panel with full 9-section underwriting.
      </div>
    </aside>
  );
}

// ── Left rail ─────────────────────────────────────────────────────────────────

function LeftRail() {
  const [tree, setTree] = useState<LayerCat[]>(INITIAL_LAYER_TREE);
  const [activeDeal, setActiveDeal] = useState("d2");
  const [dateRange, setDateRange] = useState("24 m");

  function toggleCat(k: string) {
    setTree(t => t.map(c => c.key === k ? { ...c, open: !c.open } : c));
  }

  return (
    <aside className="layer-panel" style={{ width: 260 }}>
      {/* Saved Deals */}
      <div className="layer-section">
        <div className="hd">Saved Deals</div>
        {SAVED_DEALS.map(d => (
          <div key={d.id} className={"saved-deal " + (d.id === activeDeal ? "active" : "")} onClick={() => setActiveDeal(d.id)}>
            <div className="thumb" aria-hidden="true">
              <svg viewBox="0 0 40 40" style={{ width: "100%", height: "100%" }}>
                <rect width="40" height="40" fill="#F0F0F0" />
                <polygon
                  points={d.id === "d1" ? "6,12 30,8 34,28 14,32" : d.id === "d2" ? "10,10 30,12 28,30 12,28" : d.id === "d3" ? "8,8 32,10 30,32 8,28" : d.id === "d4" ? "6,14 28,8 34,24 18,32" : "10,12 32,16 28,30 8,26"}
                  fill={d.id === activeDeal ? "var(--brand-navy)" : "#C8C8C8"}
                  fillOpacity={d.id === activeDeal ? 0.35 : 0.6}
                  stroke={d.id === activeDeal ? "var(--brand-navy)" : "#888"}
                  strokeWidth="1"
                />
              </svg>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="lbl">{d.label}</div>
              <div className="sub">{d.district} · <span style={{ color: d.days === 0 ? "var(--up)" : "var(--text-tertiary)" }}>{d.days === 0 ? "updated today" : `${d.days}d ago`}</span></div>
            </div>
          </div>
        ))}
        <a className="how-link" href="#" style={{ marginTop: 8 }}>+ Save current view as deal</a>
      </div>

      {/* Map Layers */}
      <div className="layer-section">
        <div className="hd">Map Layers</div>
        {tree.map(cat => (
          <div key={cat.key}>
            <div className="layer-row" onClick={() => toggleCat(cat.key)} style={{ cursor: "pointer" }}>
              <span style={{ flex: 1, fontWeight: 500, fontSize: 12, color: "var(--text-primary)" }}>{cat.label}</span>
              <span className="chev">{cat.open ? "▾" : "▸"}</span>
            </div>
            {cat.open && cat.children.map((ch, i) => (
              <div key={i} className="layer-row sub">
                <span className={"cbox " + (ch.on ? "on" : "")} />
                <span>{ch.label}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="layer-section">
        <div className="hd">Filters</div>
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 6 }}>Date range</div>
        <div style={{ display: "flex", gap: 4, marginBottom: 14, flexWrap: "wrap" }}>
          {["6 m", "12 m", "24 m", "5 yr"].map(r => (
            <span key={r} className={"chip" + (dateRange === r ? " active" : "")} onClick={() => setDateRange(r)}>{r}</span>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 6 }}>Plot price PLN/m²</div>
        <div className="mono tnum" style={{ fontSize: 12, marginBottom: 6 }}>800 — 4,500</div>
        <div style={{ height: 4, background: "#F0F0F0", position: "relative" }}>
          <div style={{ position: "absolute", left: "15%", right: "35%", top: 0, bottom: 0, background: "var(--brand-navy)" }} />
        </div>
      </div>
    </aside>
  );
}

// ── Map controls ──────────────────────────────────────────────────────────────

function MapControls({ compareOn, onToggle }: { compareOn: boolean; onToggle: () => void }) {
  return (
    <div style={{ position: "absolute", top: 14, right: 14, display: "flex", flexDirection: "column", gap: 6, zIndex: 10 }}>
      <button className="map-ctl">+</button>
      <button className="map-ctl">−</button>
      <button className="map-ctl" title="Locate">⊕</button>
      <button className={"map-ctl wide " + (compareOn ? "on" : "")} onClick={onToggle}>Compare</button>
      <button className="map-ctl wide">Fullscreen</button>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const WARSAW = { longitude: 21.017, latitude: 52.237, zoom: 13 };

export function WorkbenchPage() {
  const mapRef = useRef<MapRef>(null);
  const [compareOn, setCompareOn] = useState(false);

  return (
    <div style={{ display: "flex", height: "calc(100vh - 100px)", background: "#fff", overflow: "hidden" }}>
      <LeftRail />

      {/* Map */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden", borderRight: "1px solid var(--border)" }}>
        <Map
          ref={mapRef}
          initialViewState={WARSAW}
          style={{ width: "100%", height: "100%" }}
          mapStyle="https://tiles.openfreemap.org/styles/liberty"
        >
          <NavigationControl position="top-left" showCompass={false} />
        </Map>

        {/* Plot pin overlay */}
        <div style={{
          position: "absolute", top: "38%", left: "32%", pointerEvents: "none",
          padding: "6px 10px", background: "#fff", border: "1px solid var(--brand-navy)",
          fontSize: 11, fontWeight: 500, color: "var(--brand-navy)",
          boxShadow: "0 2px 8px rgba(0,32,96,0.15)",
        }}>
          ul. Towarowa 28 · Wola
        </div>

        <MapControls compareOn={compareOn} onToggle={() => setCompareOn(v => !v)} />
      </div>

      {/* Right rail */}
      {compareOn ? <PlotCompareView /> : <PlotEvaluation />}
    </div>
  );
}
