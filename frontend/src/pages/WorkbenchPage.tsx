// Workbench V2 — three-pane: 260px saved-deals/layers | map | 480px PlotEvaluation

import { useEffect, useRef, useState } from "react";
import Map, { NavigationControl, type MapRef } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { api } from "../lib/api";

// ── Saved deals registry ───────────────────────────────────────────────────────
const SAVED_DEALS = [
  { id: "d1", label: "Białołęka greenfield 14ha", district: "Białołęka",  days: 2,  plotId: null              },
  { id: "d2", label: "ul. Towarowa 28 — Wola",    district: "Wola",       days: 0,  plotId: "demo-towarowa-28" },
  { id: "d3", label: "Mokotów Służewiec PRS",     district: "Mokotów",    days: 5,  plotId: null              },
  { id: "d4", label: "Praga-Płd. Kamionek plot",  district: "Praga-Płd",  days: 11, plotId: null              },
  { id: "d5", label: "Wilanów North 8ha",         district: "Wilanów",    days: 18, plotId: null              },
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

// ── POI layer configuration ────────────────────────────────────────────────────

// Maps infra layer label → OSM category fetched from /api/workbench/pois
const INFRA_POI: Record<string, string> = {
  "Metro + planned extensions": "metro_station",
  "Tram": "tram_stop",
  "Schools": "school",
  "Hospitals": "healthcare",
  "Parks": "park",
};

const POI_LAYER_STYLE: Record<string, { color: string; radius: number; opacity: number }> = {
  metro_station: { color: "#002060", radius: 6, opacity: 0.9 },
  tram_stop:     { color: "#002060", radius: 3, opacity: 0.7 },
  school:        { color: "#14326D", radius: 5, opacity: 0.75 },
  healthcare:    { color: "#8B1F1F", radius: 5, opacity: 0.75 },
  park:          { color: "#1F6B3A", radius: 4, opacity: 0.6 },
};

// ── API types ──────────────────────────────────────────────────────────────────

interface ZoningParams {
  max_far: number | null;
  max_height_m: number | null;
  max_site_coverage_pct: number | null;
  min_greenery_pct: number | null;
  min_parking_ratio: number | null;
  front_setback_m: number | null;
}
interface SectionA {
  status: string;
  mpzp_name: string;
  mpzp_enacted_date: string;
  mpzp_resolution_id: string;
  function_code: string;
  parameters: ZoningParams;
  notes: string;
  source: string;
}
interface LandComp { date: string; distance_m: number; area_m2: number; pln_per_m2: number; market_type: string; source: string; }
interface ScatterDot { date: string; pln_per_m2: number; area_m2: number; }
interface SectionB {
  median_pln_m2: number | null;
  comparable_tx_count: number;
  total_m2_traded: number;
  scatter_data: ScatterDot[];
  top_comps: LandComp[];
}
interface SectionC {
  primary_market: { median_pln_m2: number | null; change_30d_pct: number | null; n_units: number; source: string; };
  secondary_market: { median_pln_m2: number; change_12m_pct: number; source: string; };
  projected_exit_24m: { growth_rate_pct: number; conservative: number | null; central: number | null; optimistic: number | null; };
}
interface SupplyProject {
  developer_name: string; investment_name: string; distance_m: number; units: number;
  completion_target: string; pln_m2: number; units_sold_to_date: number; monthly_absorption: number;
}
interface SectionD {
  pipeline_units: number; delivering_24mo_units: number; avg_pln_m2: number | null;
  top_projects: SupplyProject[];
}
interface SectionE {
  district: string; population_current: number; population_5y_trajectory_pct: number;
  age_25_44_share_pct: number; age_25_44_vs_warsaw_avg_pct: number;
  avg_monthly_earnings_pln: number; earnings_3y_trajectory_pct: number;
  dwellings_per_1000: number; supply_status: string;
}
interface SectionF {
  nearest_metro: string; metro_distance_min: number;
  nearest_tram: string; tram_distance_min: number;
  planned_transport: string; schools_1km_count: number; healthcare_2km_count: number;
}
interface RegItem { event_date: string; title: string; source: string; link_url: string | null; }
interface SectionG { items: RegItem[]; }
interface IntelItem {
  timestamp: string; type: string; headline: string; source: string; confidence: number;
  dpct?: number; prev_m2?: number; curr_m2?: number; unit_count?: number;
}
interface SectionH { items: IntelItem[]; }
interface SectionIOutputs {
  estimated_gdv_pln: number; estimated_total_cost_pln: number;
  residual_land_value_pln_m2: number; residual_land_value_total_pln: number;
}
interface SectionI {
  inputs: { build_cost_pln_m2_pum: number; target_irr_pct: number; financing_ltv_pct: number;
            financing_rate_premium_bps: number; sales_velocity_units_per_month: number; build_duration_months: number; };
  derived: { pum_m2: number; central_exit_price_pln_m2: number; };
  outputs: SectionIOutputs;
  sensitivity_matrix: { hp_lc: number; hp_hc: number; lp_lc: number; lp_hc: number; };
}
interface PlotMeta { plot_id: string; address: string; district: string; area_m2: number; kw_number: string; summary: string; }
interface PlotEvalData {
  plot: PlotMeta;
  section_a_zoning: SectionA;
  section_b_land_comps: SectionB;
  section_c_exit_pricing: SectionC;
  section_d_competing_supply: SectionD;
  section_e_demographics: SectionE;
  section_f_infrastructure: SectionF;
  section_g_regulatory: SectionG;
  section_h_recent_intelligence: SectionH;
  section_i_underwriting_snapshot: SectionI;
}

// ── Static fallback for compare view ──────────────────────────────────────────
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

function CompsScatter({ data, median }: { data: ScatterDot[]; median: number }) {
  const W = 420, H = 120, pad = 22;
  if (!data.length) return null;
  const prices = data.map(d => d.pln_per_m2);
  const minP = Math.min(...prices) * 0.95;
  const maxP = Math.max(...prices) * 1.05;
  const x = (i: number) => pad + (i / Math.max(data.length - 1, 1)) * (W - pad * 2);
  const y = (v: number) => H - pad - ((v - minP) / (maxP - minP)) * (H - pad * 2);
  const gridVals = [
    Math.round(minP / 500) * 500,
    Math.round((minP + (maxP - minP) / 3) / 500) * 500,
    Math.round((minP + (maxP - minP) * 2 / 3) / 500) * 500,
    Math.round(maxP / 500) * 500,
  ].filter((v, i, arr) => arr.indexOf(v) === i);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      {gridVals.map(v => (
        <g key={v}>
          <line x1={pad} x2={W - pad} y1={y(v)} y2={y(v)} stroke="#F0F0F0" />
          <text x={2} y={y(v) + 3} fontSize="9" fill="var(--text-tertiary)" fontFamily="IBM Plex Mono">{(v / 1000).toFixed(1)}k</text>
        </g>
      ))}
      <line x1={pad} x2={W - pad} y1={y(median)} y2={y(median)} stroke="var(--brand-navy)" strokeWidth="1" strokeDasharray="2 2" />
      <text x={W - pad - 1} y={y(median) - 3} fontSize="9" fill="var(--brand-navy)" textAnchor="end">median {(median / 1000).toFixed(2)}k</text>
      {data.map((d, i) => (
        <circle key={i} cx={x(i)} cy={y(d.pln_per_m2)} r={Math.sqrt(d.area_m2) / 12}
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

// ── Skeleton loader ────────────────────────────────────────────────────────────

function SkeletonBlock({ h = 16, w = "100%" }: { h?: number; w?: string | number }) {
  return <div style={{ height: h, width: w, background: "var(--bg-wash)", borderRadius: 3, marginBottom: 6, animation: "pulse 1.4s ease-in-out infinite" }} />;
}

function PlotEvalSkeleton() {
  return (
    <aside className="eval-panel" style={{ width: 480 }}>
      <div className="pe-id-strip">
        <SkeletonBlock h={14} w="40%" />
        <SkeletonBlock h={20} w="80%" />
        <SkeletonBlock h={11} w="55%" />
        <SkeletonBlock h={11} w="70%" />
      </div>
      {[...Array(4)].map((_, i) => (
        <div key={i} className="pe-section">
          <SkeletonBlock h={12} w="30%" />
          <SkeletonBlock h={11} />
          <SkeletonBlock h={11} />
          <SkeletonBlock h={11} w="70%" />
        </div>
      ))}
    </aside>
  );
}

// ── Underwriting (Section I) — reads from API data ────────────────────────────

function Underwriting({ sec }: { sec: SectionI }) {
  const { inputs, derived, outputs, sensitivity_matrix: sm } = sec;
  const fmtM = (v: number) => (v / 1_000_000).toLocaleString("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const fmtInt = (v: number) => Math.round(v).toLocaleString("pl-PL");

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
            <div className="pe-uw-out-gdv tnum">PLN {fmtM(outputs.estimated_gdv_pln)}M</div>
          </div>
          <div className="pe-uw-out-block" style={{ marginTop: 10 }}>
            <div className="pe-uw-out-label">Estimated total cost</div>
            <div className="pe-uw-out-cost tnum">PLN {fmtM(outputs.estimated_total_cost_pln)}M</div>
          </div>
          <div className="pe-uw-rule" />
          <div className="pe-uw-out-label">Max land price at target IRR</div>
          <div className="pe-uw-residual tnum">
            PLN {fmtInt(outputs.residual_land_value_pln_m2)}
            <span className="pe-uw-residual-unit">/m²</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
            Total: PLN {fmtM(outputs.residual_land_value_total_pln)}M for {derived.pum_m2.toLocaleString("pl-PL")} m² PUM
          </div>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", margin: "18px 0 6px" }}>
            Sensitivity (±5% price × ±10% cost)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            <SensCell v={sm.hp_lc} tone="good" />
            <SensCell v={sm.hp_hc} />
            <SensCell v={sm.lp_lc} />
            <SensCell v={sm.lp_hc} tone="bad" />
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
          <InputRow label="Build cost"     sub="PLN/m² PUM"        value={fmtInt(inputs.build_cost_pln_m2_pum)} />
          <InputRow label="Target IRR"     sub="%"                 value={inputs.target_irr_pct} />
          <InputRow label="Financing"      sub="% LTV · WIBOR+2.5" value={`${inputs.financing_ltv_pct}%`} />
          <InputRow label="Sales velocity" sub="units / mo"        value={inputs.sales_velocity_units_per_month} />
          <InputRow label="Build duration" sub="months"            value={inputs.build_duration_months} />
        </div>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-tertiary)", lineHeight: 1.5, marginTop: 18 }}>
        This is a screening tool. Always run a full underwrite before committing capital.
      </div>
    </div>
  );
}

// ── PlotEvaluation panel ──────────────────────────────────────────────────────

function PlotEvaluation({ data }: { data: PlotEvalData }) {
  const [saved, setSaved] = useState(true);
  const { plot: p, section_a_zoning: a, section_b_land_comps: b, section_c_exit_pricing: c,
          section_d_competing_supply: d, section_e_demographics: e, section_f_infrastructure: f,
          section_g_regulatory: g, section_h_recent_intelligence: h, section_i_underwriting_snapshot: sec_i } = data;

  const supplyLabel = e.supply_status === "under_supplied"
    ? { label: "under-supplied", color: "var(--up)", bg: "#ECF2EC" }
    : e.supply_status === "over_supplied"
    ? { label: "over-supplied", color: "var(--down)", bg: "#F2ECEC" }
    : { label: "balanced", color: "var(--warn)", bg: "#F2EFE6" };

  const fmtN = (v: number) => v.toLocaleString("pl-PL");
  const fmtDate = (iso: string) => {
    const d2 = new Date(iso);
    return d2.toLocaleDateString("pl-PL", { day: "2-digit", month: "short", year: "2-digit" }).replace(" ", " ").replace(" ", " ");
  };

  return (
    <aside className="eval-panel" style={{ width: 480 }}>
      {/* Plot identifier strip */}
      <div className="pe-id-strip">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Plot Evaluation · {p.district.charAt(0).toUpperCase() + p.district.slice(1)}</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-heading)", marginTop: 4 }}>ul. Towarowa 28 — Wola</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3, fontFamily: "IBM Plex Mono" }}>KW {p.kw_number}</div>
          </div>
          <button className={"pe-star " + (saved ? "on" : "")} onClick={() => setSaved(!saved)} title="Save deal">★</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 10 }}>{p.address}</div>
        <div style={{ fontSize: 12, color: "var(--text-primary)", marginTop: 4 }}>
          <span className="tnum">{fmtN(p.area_m2)}</span> m² · {p.summary}
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
        <div className={`pe-status ${a.status === "mpzp_enacted" ? "pe-status-ok" : "pe-status-warn"}`}>
          <span className="dot" /> MPZP enacted · {a.mpzp_name} · {a.mpzp_enacted_date ? new Date(a.mpzp_enacted_date).toLocaleDateString("pl-PL", { day: "numeric", month: "short", year: "numeric" }) : "—"}
        </div>
        <KV rows={[
          ["Function code",     a.function_code],
          ["Max FAR",           <span className="tnum">{a.parameters.max_far ?? "—"}</span>],
          ["Max height",        <span><span className="tnum">{a.parameters.max_height_m ?? "—"}</span> m</span>],
          ["Max site coverage", <span><span className="tnum">{a.parameters.max_site_coverage_pct ?? "—"}</span>%</span>],
          ["Min greenery",      <span><span className="tnum">{a.parameters.min_greenery_pct ?? "—"}</span>%</span>],
          ["Min parking ratio", <span><span className="tnum">{a.parameters.min_parking_ratio ?? "—"}</span> per unit</span>],
          ["Front setback",     <span><span className="tnum">{a.parameters.front_setback_m ?? "—"}</span> m</span>],
        ]} />
        {a.notes && (
          <div className="source-quote">
            {a.notes}
            {a.mpzp_resolution_id && <span className="source-attr">— {a.mpzp_resolution_id}</span>}
          </div>
        )}
        <a className="how-link" href="#">View MPZP text · PL ↔ EN</a>
      </div>

      {/* B — Land Comps */}
      <div className="pe-section">
        <SectionHd letter="B" title="Land comparable transactions" subtitle="Last 24 months · 1 km radius · RCN" />
        <div className="pe-stat-row">
          <div className="stat"><div className="v tnum">{b.median_pln_m2 ? fmtN(b.median_pln_m2) : "—"}</div><div className="l">PLN/m² median</div></div>
          <div className="stat"><div className="v tnum">{b.comparable_tx_count}</div><div className="l">comparable tx</div></div>
          <div className="stat"><div className="v tnum">{(b.total_m2_traded / 1000).toFixed(1)}k</div><div className="l">m² traded</div></div>
        </div>
        {b.scatter_data.length > 0 && b.median_pln_m2 && (
          <div style={{ marginTop: 12, marginBottom: 8 }}>
            <CompsScatter data={b.scatter_data} median={b.median_pln_m2} />
          </div>
        )}
        <table className="pe-table">
          <thead>
            <tr><th>Date</th><th className="num">Dist</th><th className="num">Area</th><th className="num">PLN/m²</th><th>Mkt</th></tr>
          </thead>
          <tbody>
            {b.top_comps.map((comp, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 11 }}>{fmtDate(comp.date)}</td>
                <td className="num"><span className="tnum">{comp.distance_m}</span> m</td>
                <td className="num tnum">{fmtN(comp.area_m2)}</td>
                <td className="num tnum"><strong>{fmtN(comp.pln_per_m2)}</strong></td>
                <td style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "capitalize" }}>{comp.market_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <a className="how-link" href="#">How comps are selected</a>
      </div>

      {/* C — Apartment Exit */}
      <div className="pe-section">
        <SectionHd letter="C" title="Apartment exit pricing" subtitle="Wola district · Jawność cen + RCN" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div className="pe-mini-card">
            <div className="t">Primary market</div>
            <div className="v tnum">{c.primary_market.median_pln_m2 ? fmtN(c.primary_market.median_pln_m2) : "—"} <span className="u">PLN/m²</span></div>
            {c.primary_market.change_30d_pct !== null && (
              <div className="d" style={{ color: (c.primary_market.change_30d_pct ?? 0) >= 0 ? "var(--up)" : "var(--down)" }}>
                {(c.primary_market.change_30d_pct ?? 0) >= 0 ? "+" : ""}{c.primary_market.change_30d_pct}% · 30d
              </div>
            )}
          </div>
          <div className="pe-mini-card">
            <div className="t">Secondary market</div>
            <div className="v tnum">{fmtN(c.secondary_market.median_pln_m2)} <span className="u">PLN/m²</span></div>
            <div className="d" style={{ color: "var(--up)" }}>+{c.secondary_market.change_12m_pct}% · 12m</div>
          </div>
        </div>
        <div style={{ marginTop: 14, padding: "12px 14px", background: "var(--bg-wash)", border: "1px solid var(--border)" }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>
            Projected exit · 24 months · @ {c.projected_exit_24m.growth_rate_pct}% / yr
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <div><div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Conservative</div><div className="tnum" style={{ fontSize: 14, fontWeight: 500 }}>{c.projected_exit_24m.conservative ? fmtN(c.projected_exit_24m.conservative) : "—"}</div></div>
            <div><div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Central</div><div className="tnum" style={{ fontSize: 14, fontWeight: 500, color: "var(--brand-navy)" }}>{c.projected_exit_24m.central ? fmtN(c.projected_exit_24m.central) : "—"}</div></div>
            <div><div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Optimistic</div><div className="tnum" style={{ fontSize: 14, fontWeight: 500 }}>{c.projected_exit_24m.optimistic ? fmtN(c.projected_exit_24m.optimistic) : "—"}</div></div>
          </div>
        </div>
      </div>

      {/* D — Competing Supply */}
      <div className="pe-section">
        <SectionHd letter="D" title="Competing residential supply" subtitle="Wola district · Jawność pipeline" />
        <div className="pe-stat-row">
          <div className="stat"><div className="v tnum">{fmtN(d.pipeline_units)}</div><div className="l">units in pipeline</div></div>
          <div className="stat"><div className="v tnum">{fmtN(d.delivering_24mo_units)}</div><div className="l">deliver ≤24 m</div></div>
          <div className="stat"><div className="v tnum">{d.avg_pln_m2 ? fmtN(d.avg_pln_m2) : "—"}</div><div className="l">avg PLN/m²</div></div>
        </div>
        <table className="pe-table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ minWidth: 80 }}>Developer</th><th>Project</th>
              <th className="num">Dist</th><th className="num">Units</th>
              <th>Compl.</th><th className="num">PLN/m²</th>
              <th className="num">Sold</th><th className="num">/mo</th>
            </tr>
          </thead>
          <tbody>
            {d.top_projects.map((proj, i) => (
              <tr key={i}>
                <td style={{ fontSize: 11, fontWeight: 500, maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{proj.developer_name}</td>
                <td style={{ fontSize: 10, color: "var(--text-secondary)", maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{proj.investment_name}</td>
                <td className="num tnum">{fmtN(proj.distance_m)} m</td>
                <td className="num tnum">{proj.units}</td>
                <td className="mono" style={{ fontSize: 10, color: "var(--text-secondary)" }}>{proj.completion_target}</td>
                <td className="num tnum"><strong>{fmtN(proj.pln_m2)}</strong></td>
                <td className="num tnum">{proj.units_sold_to_date}</td>
                <td className="num tnum">{proj.monthly_absorption.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <a className="how-link" href="#" style={{ marginTop: 6, display: "inline-block" }}>View all on map</a>
      </div>

      {/* E — Demographics */}
      <div className="pe-section">
        <SectionHd letter="E" title="Demographics & macro" subtitle={`${e.district.charAt(0).toUpperCase() + e.district.slice(1)} · GUS BDL`} />
        <div className="kv">
          <div className="k">Population</div>
          <div className="v">
            <span className="tnum">{fmtN(e.population_current)}</span>
            <span style={{ display: "block", fontSize: 10, color: "var(--up)", marginTop: 1 }}>+{e.population_5y_trajectory_pct}% · 5y</span>
          </div>
          <div className="k">Age 25–44</div>
          <div className="v">
            <span className="tnum">{e.age_25_44_share_pct}%</span>
            <span style={{ display: "block", fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>Warsaw avg {e.age_25_44_vs_warsaw_avg_pct}%</span>
          </div>
          <div className="k">Avg gross / mo</div>
          <div className="v">
            PLN <span className="tnum">{fmtN(e.avg_monthly_earnings_pln)}</span>
            <span style={{ display: "block", fontSize: 10, color: "var(--up)", marginTop: 1 }}>+{e.earnings_3y_trajectory_pct}% · 3y</span>
          </div>
          <div className="k">Dwellings / 1,000</div>
          <div className="v">
            <span className="tnum">{e.dwellings_per_1000}</span>
            <span style={{ display: "inline-block", marginLeft: 8, padding: "2px 6px", fontSize: 10, fontWeight: 500,
              background: supplyLabel.bg, color: supplyLabel.color,
              textTransform: "uppercase", letterSpacing: "0.3px", verticalAlign: "middle" }}>
              {supplyLabel.label}
            </span>
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 14 }}>GUS BDL · 2025 Q4</div>
      </div>

      {/* F — Infrastructure */}
      <div className="pe-section">
        <SectionHd letter="F" title="Infrastructure" subtitle="Distance to amenities" />
        <div className="kv">
          <div className="k">Nearest metro</div>
          <div className="v">{f.nearest_metro} · <span className="tnum">{f.metro_distance_min}</span> min walk</div>
          <div className="k">Nearest tram</div>
          <div className="v">{f.nearest_tram} · <span className="tnum">{f.tram_distance_min}</span> min walk</div>
          <div className="k">Schools (1 km)</div>
          <div className="v tnum">{f.schools_1km_count}</div>
          <div className="k">Healthcare (2 km)</div>
          <div className="v tnum">{f.healthcare_2km_count}</div>
        </div>
        {f.planned_transport && (
          <>
            <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", margin: "16px 0 6px" }}>Planned transport</div>
            <div style={{ padding: "9px 0", borderTop: "1px solid var(--divider)", fontSize: 12, color: "var(--text-primary)", lineHeight: 1.4 }}>
              {f.planned_transport}
            </div>
          </>
        )}
      </div>

      {/* G — Regulatory */}
      <div className="pe-section">
        <SectionHd letter="G" title="Regulatory & political" subtitle={`Risk indicators · ${e.district.charAt(0).toUpperCase() + e.district.slice(1)}`} />
        {g.items.map((item, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "72px 1fr 14px", gap: 10, padding: "10px 0", borderTop: i ? "1px solid var(--divider)" : "none", alignItems: "flex-start" }}>
            <div>
              <div className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{fmtDate(item.event_date)}</div>
              <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.3px", marginTop: 2 }}>{(item.source.split("/")[0] ?? item.source).trim()}</div>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-primary)", lineHeight: 1.4 }}>{item.title}</div>
            {item.link_url
              ? <a href={item.link_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--text-tertiary)", textAlign: "right" }}>↗</a>
              : <span style={{ fontSize: 11, color: "var(--border)", textAlign: "right" }}>↗</span>
            }
          </div>
        ))}
      </div>

      {/* H — Recent Intelligence */}
      <div className="pe-section">
        <SectionHd letter="H" title="Recent intelligence" subtitle={`Last 30 days · ${e.district.charAt(0).toUpperCase() + e.district.slice(1)} + residential primary`} />
        {h.items.length === 0 ? (
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "10px 0" }}>No price-change events in last 30 days.</div>
        ) : h.items.map((item, i) => (
          <div key={i} style={{ padding: "11px 0", borderTop: i ? "1px solid var(--divider)" : "none" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{fmtDate(item.timestamp)}</span>
              <span className={"type-pill " + item.type} style={{ fontSize: 9 }}>{item.type}</span>
              <span style={{ marginLeft: "auto" }}><ConfDots n={item.confidence} /></span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-primary)", lineHeight: 1.45 }}>{item.headline}</div>
            <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 3 }}>{item.source}</div>
          </div>
        ))}
      </div>

      {/* I — Underwriting */}
      <Underwriting sec={sec_i} />

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

function PlotCol({ p, isA, liveData }: { p: typeof PLOT_B; isA: boolean; liveData?: PlotEvalData | undefined }) {
  const fmtN = (v: number) => v.toLocaleString("pl-PL");

  if (isA && liveData) {
    const ld = liveData;
    return (
      <div style={{ flex: 1, padding: "18px 20px", borderRight: "1px solid var(--border)", minWidth: 0, overflowY: "auto" }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Plot A</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-heading)", marginTop: 4 }}>ul. Towarowa 28 — Wola</div>
        <div className="mono" style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 3 }}>KW {ld.plot.kw_number}</div>
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>{ld.plot.address}</div>
        <div style={{ fontSize: 11, marginTop: 4 }}><span className="tnum">{fmtN(ld.plot.area_m2)}</span> m² · {ld.plot.district.charAt(0).toUpperCase() + ld.plot.district.slice(1)}</div>
        <div style={{ marginTop: 14, padding: "8px 10px", background: "#ECF2EC", border: "1px solid rgba(31,107,58,0.2)", fontSize: 11, lineHeight: 1.4 }}>
          <div style={{ fontWeight: 500, color: "var(--up)" }}>● MPZP enacted</div>
          <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>{ld.section_a_zoning.mpzp_name}</div>
          <div style={{ marginTop: 4 }}>FAR <span className="tnum">{ld.section_a_zoning.parameters.max_far}</span> · H <span className="tnum">{ld.section_a_zoning.parameters.max_height_m}</span>m · {ld.section_a_zoning.function_code}</div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Land comp</div>
          <div className="tnum" style={{ fontSize: 18, fontWeight: 500 }}>{ld.section_b_land_comps.median_pln_m2 ? fmtN(ld.section_b_land_comps.median_pln_m2) : "—"} <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 400 }}>PLN/m²</span></div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>median · {ld.section_b_land_comps.comparable_tx_count} comps · 1 km</div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Apt exit (primary)</div>
          <div className="tnum" style={{ fontSize: 18, fontWeight: 500 }}>{ld.section_c_exit_pricing.primary_market.median_pln_m2 ? fmtN(ld.section_c_exit_pricing.primary_market.median_pln_m2) : "—"} <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 400 }}>PLN/m²</span></div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Competing supply</div>
          <div className="tnum" style={{ fontSize: 14, fontWeight: 500 }}>{fmtN(ld.section_d_competing_supply.pipeline_units)} units</div>
        </div>
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--divider)" }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Demographics</div>
          <div style={{ fontSize: 11, lineHeight: 1.6 }}>
            Pop <span className="tnum">{fmtN(ld.section_e_demographics.population_current)}</span> · <span style={{ color: "var(--up)" }}>+{ld.section_e_demographics.population_5y_trajectory_pct}% 5y</span><br />
            Age 25–44 <span className="tnum">{ld.section_e_demographics.age_25_44_share_pct}%</span><br />
            Avg inc PLN <span className="tnum">{fmtN(ld.section_e_demographics.avg_monthly_earnings_pln)}</span>/mo
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Transit</div>
          <div style={{ fontSize: 11 }}>{ld.section_f_infrastructure.nearest_metro}</div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{ld.section_f_infrastructure.metro_distance_min} min walk</div>
        </div>
        <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--bg-wash)", fontSize: 11, lineHeight: 1.5 }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 4 }}>Signal</div>
          Short-cycle infill. Premium PUM, fully entitled.
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, padding: "18px 20px", borderRight: isA ? "1px solid var(--border)" : "none", minWidth: 0, overflowY: "auto" }}>
      <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{isA ? "Plot A" : "Plot B"}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-heading)", marginTop: 4, lineHeight: 1.3 }}>{p.label}</div>
      <div className="mono" style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 3 }}>KW {p.kw}</div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.4 }}>{p.address}</div>
      <div style={{ fontSize: 11, color: "var(--text-primary)", marginTop: 4 }}>
        <span className="tnum">{fmtN(p.area_m2)}</span> m² · {p.district}
      </div>
      <div style={{ marginTop: 14, padding: "8px 10px", background: "#FFF8E1", border: "1px solid rgba(180,138,0,0.2)", fontSize: 11 }}>
        <div style={{ fontWeight: 500, color: "#8B6914" }}>▲ No MPZP</div>
        <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>{p.mpzp.name}</div>
        <div style={{ marginTop: 4 }}>FAR <span className="tnum">{p.mpzp.far}</span> · H <span className="tnum">{p.mpzp.height}</span>m · {p.mpzp.fn}</div>
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
        <div style={{ fontSize: 11, lineHeight: 1.6 }}>
          Pop <span className="tnum">{fmtN(p.demo.pop)}</span> · <span style={{ color: "var(--up)" }}>+{p.demo.pop_5y}% 5y</span><br />
          Age 25–44 <span className="tnum">{p.demo.age2544}%</span><br />
          Avg inc PLN <span className="tnum">{fmtN(p.demo.income)}</span>/mo
        </div>
      </div>
      <div style={{ marginTop: 14 }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 6 }}>Transit</div>
        <div style={{ fontSize: 11 }}>{p.metro}</div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{fmtN(p.metroDist)} m walk</div>
      </div>
      <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--bg-wash)", fontSize: 11, lineHeight: 1.5 }}>
        <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 4 }}>Signal</div>
        {p.signal}
      </div>
    </div>
  );
}

function PlotCompareView({ liveData }: { liveData: PlotEvalData | null }) {
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
        <PlotCol p={PLOT_B} isA={true} liveData={liveData ?? undefined} />
        <PlotCol p={PLOT_B} isA={false} />
      </div>
      <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--text-tertiary)", background: "#FAFAFA", lineHeight: 1.5, flexShrink: 0 }}>
        Toggle Compare off to return to single-plot Evaluation panel with full 9-section underwriting.
      </div>
    </aside>
  );
}

// ── Left rail ─────────────────────────────────────────────────────────────────

function LeftRail({
  activeDeal,
  onSelectDeal,
  onInfraToggle,
}: {
  activeDeal: string;
  onSelectDeal: (id: string) => void;
  onInfraToggle: (category: string, on: boolean) => void;
}) {
  const [tree, setTree] = useState<LayerCat[]>(INITIAL_LAYER_TREE);
  const [dateRange, setDateRange] = useState("24 m");

  function toggleCat(k: string) {
    setTree(t => t.map(c => c.key === k ? { ...c, open: !c.open } : c));
  }

  function toggleChild(catKey: string, childIdx: number) {
    setTree(t => t.map(cat => {
      if (cat.key !== catKey) return cat;
      const children = cat.children.map((ch, i) => {
        if (i !== childIdx) return ch;
        const next = { ...ch, on: !ch.on };
        const poiCat = INFRA_POI[ch.label];
        if (catKey === "infra" && poiCat) {
          onInfraToggle(poiCat, next.on);
        }
        return next;
      });
      return { ...cat, children };
    }));
  }

  return (
    <aside className="layer-panel" style={{ width: 260 }}>
      {/* Saved Deals */}
      <div className="layer-section">
        <div className="hd">Saved Deals</div>
        {SAVED_DEALS.map(d => (
          <div key={d.id} className={"saved-deal " + (d.id === activeDeal ? "active" : "")} onClick={() => onSelectDeal(d.id)}>
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
              <div
                key={i}
                className="layer-row sub"
                style={{ cursor: "pointer" }}
                onClick={() => toggleChild(cat.key, i)}
              >
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
  const [activeDeal, setActiveDeal] = useState("d2");
  const [plotData, setPlotData] = useState<PlotEvalData | null>(null);
  const [plotLoading, setPlotLoading] = useState(false);
  const [plotError, setPlotError] = useState<string | null>(null);

  // POI layer state
  const [mapLoaded, setMapLoaded] = useState(false);
  const [poiEnabled, setPoiEnabled] = useState<Record<string, boolean>>({ metro_station: true });
  const [poiData, setPoiData] = useState<Record<string, { type: string; features: unknown[] }>>({});

  function handleInfraToggle(category: string, on: boolean) {
    setPoiEnabled(prev => ({ ...prev, [category]: on }));
  }

  // Fetch POI GeoJSON for newly-enabled categories
  useEffect(() => {
    const toFetch = Object.entries(poiEnabled)
      .filter(([, on]) => on)
      .map(([cat]) => cat)
      .filter(cat => !poiData[cat]);
    if (!toFetch.length) return;

    const token = localStorage.getItem("ws_token");
    fetch(`/api/workbench/pois?categories=${toFetch.join(",")}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.json())
      .then((fc: { type: string; features: { properties: { category: string } }[] }) => {
        const byCat: Record<string, { type: string; features: unknown[] }> = {};
        for (const cat of toFetch) byCat[cat] = { type: "FeatureCollection", features: [] };
        for (const f of fc.features) {
          const cat = f.properties.category;
          if (byCat[cat]) byCat[cat].features.push(f);
        }
        setPoiData(prev => ({ ...prev, ...byCat }));
      })
      .catch(err => console.error("POI fetch failed:", err));
  }, [poiEnabled]);

  // Sync MapLibre layers when data or visibility changes
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !mapLoaded) return;

    for (const [cat, style] of Object.entries(POI_LAYER_STYLE)) {
      const sourceId = `poi-${cat}`;
      const layerId = `poi-layer-${cat}`;
      const on = !!poiEnabled[cat];
      const data = poiData[cat];

      if (on && data) {
        if (!map.getSource(sourceId)) {
          map.addSource(sourceId, { type: "geojson", data } as Parameters<typeof map.addSource>[1]);
          map.addLayer({
            id: layerId,
            type: "circle",
            source: sourceId,
            paint: {
              "circle-color": style.color,
              "circle-radius": style.radius,
              "circle-opacity": style.opacity,
            },
          });
        } else {
          (map.getSource(sourceId) as unknown as { setData: (d: unknown) => void }).setData(data);
          if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", "visible");
        }
      } else if (!on && map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", "none");
      }
    }
  }, [poiData, poiEnabled, mapLoaded]);

  // Fetch plot evaluation when active deal changes
  useEffect(() => {
    const deal = SAVED_DEALS.find(d => d.id === activeDeal);
    if (!deal?.plotId) {
      setPlotData(null);
      return;
    }
    const plotId = deal.plotId;
    setPlotLoading(true);
    setPlotError(null);

    api.get<PlotEvalData>(`/api/workbench/plot/${plotId}`)
      .then(data => {
        setPlotData(data);
        setPlotLoading(false);
      })
      .catch(err => {
        console.error("Plot evaluation fetch failed:", err);
        setPlotError("Plot data unavailable");
        setPlotLoading(false);
      });
  }, [activeDeal]);

  function renderRightRail() {
    if (compareOn) return <PlotCompareView liveData={plotData} />;
    if (plotLoading) return <PlotEvalSkeleton />;
    if (plotError) {
      return (
        <aside className="eval-panel" style={{ width: 480, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: 13 }}>
            <div style={{ fontSize: 20, marginBottom: 8 }}>⚠</div>
            {plotError}
          </div>
        </aside>
      );
    }
    if (plotData) return <PlotEvaluation data={plotData} />;
    return (
      <aside className="eval-panel" style={{ width: 480, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", color: "var(--text-tertiary)", fontSize: 12 }}>
          Select a saved deal to load Plot Evaluation
        </div>
      </aside>
    );
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 100px)", background: "#fff", overflow: "hidden" }}>
      <LeftRail activeDeal={activeDeal} onSelectDeal={setActiveDeal} onInfraToggle={handleInfraToggle} />

      {/* Map */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden", borderRight: "1px solid var(--border)" }}>
        <Map
          ref={mapRef}
          initialViewState={WARSAW}
          style={{ width: "100%", height: "100%" }}
          mapStyle="https://tiles.openfreemap.org/styles/liberty"
          onLoad={() => setMapLoaded(true)}
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
      {renderRightRail()}
    </div>
  );
}
