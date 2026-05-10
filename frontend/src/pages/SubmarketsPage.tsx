// Submarkets — 18 Warsaw dzielnice comparison

import { useState } from "react";

interface Dzielnica {
  n: string;
  pop: number;
  area: number;
  primaryPLN: number;
  mom: number;
  yoy: number;
  primeRentEUR: number;
  vac: number;
  yield: number;
  absorpKsqm: number;
  pipelineKsqm: number;
  footfall: string;
  liquidity: string;
}

const dzielnice: Dzielnica[] = [
  { n: "Śródmieście",    pop: 120000, area:  15.6, primaryPLN: 24800, mom: 0.8, yoy: 11.4, primeRentEUR: 28.20, vac:  5.6, yield: 5.65, absorpKsqm:  8.4, pipelineKsqm:  54, footfall: "Very high", liquidity: "AAA" },
  { n: "Mokotów",        pop: 217000, area:  35.4, primaryPLN: 18400, mom: 0.4, yoy:  7.2, primeRentEUR: 16.80, vac: 15.6, yield: 7.20, absorpKsqm:  4.6, pipelineKsqm:  21, footfall: "High",      liquidity: "AA"  },
  { n: "Wola",           pop: 142000, area:  19.3, primaryPLN: 21900, mom: 1.1, yoy: 14.8, primeRentEUR: 26.50, vac:  6.8, yield: 5.85, absorpKsqm: 18.2, pipelineKsqm: 244, footfall: "Very high", liquidity: "AAA" },
  { n: "Ochota",         pop:  84000, area:   9.7, primaryPLN: 19200, mom: 0.6, yoy:  9.4, primeRentEUR: 17.20, vac: 11.4, yield: 6.95, absorpKsqm:  1.2, pipelineKsqm:   8, footfall: "High",      liquidity: "AA"  },
  { n: "Praga-Północ",   pop:  64000, area:  11.4, primaryPLN: 16800, mom: 1.4, yoy: 18.2, primeRentEUR: 19.40, vac:  8.4, yield: 6.65, absorpKsqm:  3.8, pipelineKsqm:  34, footfall: "Med",       liquidity: "A"   },
  { n: "Praga-Południe", pop: 177000, area:  22.4, primaryPLN: 15600, mom: 1.0, yoy: 13.6, primeRentEUR: 14.50, vac:  9.2, yield: 7.10, absorpKsqm:  2.4, pipelineKsqm:  18, footfall: "Med",       liquidity: "A"   },
  { n: "Bemowo",         pop: 121000, area:  24.9, primaryPLN: 14200, mom: 0.5, yoy:  8.6, primeRentEUR: 13.00, vac: 12.0, yield: 7.40, absorpKsqm:  0.4, pipelineKsqm:   4, footfall: "Med",       liquidity: "BBB" },
  { n: "Bielany",        pop: 128000, area:  32.3, primaryPLN: 14800, mom: 0.4, yoy:  7.4, primeRentEUR: 13.40, vac: 13.2, yield: 7.45, absorpKsqm:  0.2, pipelineKsqm:   6, footfall: "Med",       liquidity: "BBB" },
  { n: "Białołęka",      pop: 139000, area:  73.0, primaryPLN: 13400, mom: 0.3, yoy:  5.8, primeRentEUR: 11.50, vac: 14.4, yield: 7.80, absorpKsqm:  0.0, pipelineKsqm:   0, footfall: "Low",       liquidity: "BB"  },
  { n: "Targówek",       pop: 122000, area:  24.4, primaryPLN: 13800, mom: 0.6, yoy:  7.0, primeRentEUR: 12.20, vac: 11.8, yield: 7.55, absorpKsqm:  0.4, pipelineKsqm:   4, footfall: "Med",       liquidity: "BB"  },
  { n: "Rembertów",      pop:  24000, area:  19.2, primaryPLN: 12400, mom: 0.2, yoy:  4.4, primeRentEUR: 10.80, vac: 18.0, yield: 8.20, absorpKsqm:  0.0, pipelineKsqm:   0, footfall: "Low",       liquidity: "BB"  },
  { n: "Wesoła",         pop:  26000, area:  22.6, primaryPLN: 12800, mom: 0.3, yoy:  5.2, primeRentEUR: 10.40, vac: 16.4, yield: 8.35, absorpKsqm:  0.0, pipelineKsqm:   0, footfall: "Low",       liquidity: "B"   },
  { n: "Wawer",          pop:  79000, area:  79.7, primaryPLN: 13600, mom: 0.5, yoy:  6.4, primeRentEUR: 11.20, vac: 15.0, yield: 7.85, absorpKsqm:  0.0, pipelineKsqm:   2, footfall: "Low",       liquidity: "BB"  },
  { n: "Ursynów",        pop: 147000, area:  43.8, primaryPLN: 16400, mom: 0.7, yoy:  9.8, primeRentEUR: 14.80, vac: 10.6, yield: 7.20, absorpKsqm:  1.4, pipelineKsqm:  12, footfall: "High",      liquidity: "A"   },
  { n: "Wilanów",        pop:  47000, area:  36.7, primaryPLN: 18200, mom: 0.9, yoy: 11.0, primeRentEUR: 15.60, vac:  9.4, yield: 7.10, absorpKsqm:  0.8, pipelineKsqm:   9, footfall: "Med",       liquidity: "A"   },
  { n: "Włochy",         pop:  43000, area:  28.6, primaryPLN: 14600, mom: 0.6, yoy:  8.0, primeRentEUR: 13.80, vac: 14.4, yield: 7.65, absorpKsqm:  0.6, pipelineKsqm:   7, footfall: "Med",       liquidity: "BBB" },
  { n: "Ursus",          pop:  60000, area:   9.4, primaryPLN: 13800, mom: 0.5, yoy:  7.6, primeRentEUR: 11.80, vac: 13.6, yield: 7.70, absorpKsqm:  0.2, pipelineKsqm:   4, footfall: "Med",       liquidity: "BB"  },
  { n: "Żoliborz",       pop:  53000, area:   8.5, primaryPLN: 18800, mom: 0.8, yoy: 10.4, primeRentEUR: 16.20, vac: 10.0, yield: 6.85, absorpKsqm:  0.6, pipelineKsqm:   5, footfall: "High",      liquidity: "AA"  },
];

const COMPARE_DISTRICTS = ["Wola", "Śródmieście", "Mokotów", "Praga-Północ"];

type SortKey = keyof Dzielnica;
type SortDir = "asc" | "desc";

const THESES = {
  resi_dev: {
    label: "Residential development play",
    blurb: "Scored for: rising prices, healthy YoY momentum, strong absorption, sufficient pipeline runway, liquid capital markets.",
    weights: { yoy: 0.30, primaryPLN: 0.20, absorpKsqm: 0.20, pipelineKsqm: 0.15, liquidity: 0.15 },
  },
  office_core: {
    label: "Office core (long-hold institutional)",
    blurb: "Low vacancy, premium rents, tight yields, strong liquidity. Favours Centrum / Wola / Mokotów triangle.",
    weights: { primeRentEUR: 0.30, vac: 0.30, yield: 0.20, liquidity: 0.20 },
  },
  value_add: {
    label: "Value-add / repositioning",
    blurb: "Mid-tier rents with rising momentum, vacancy dispersion, accessible yield. Avoids over-supplied stock.",
    weights: { yoy: 0.25, vac: 0.25, yield: 0.20, primeRentEUR: 0.15, absorpKsqm: 0.15 },
  },
  emerging: {
    label: "Emerging neighbourhood",
    blurb: "High YoY momentum off a low base. Targets pre-gentrification opportunities (Praga-Płn, Targówek, Włochy).",
    weights: { yoy: 0.40, primaryPLN: -0.20, pop: 0.15, absorpKsqm: 0.15, pipelineKsqm: 0.10 },
  },
};

const liqScore = (s: string) => ({ AAA: 5, AA: 4, A: 3, BBB: 2, BB: 1, B: 0 }[s] ?? 0);

function heatBg(val: number, min: number, max: number) {
  const t = Math.max(0, Math.min(1, (val - min) / (max - min || 1)));
  return `rgba(0, 32, 96, ${(0.06 + t * 0.36).toFixed(3)})`;
}
function heatBgInv(val: number, min: number, max: number) {
  return heatBg(max - (val - min), min, max);
}

function range(key: keyof Dzielnica): [number, number] {
  const vals = dzielnice.map(d => d[key] as number);
  return [Math.min(...vals), Math.max(...vals)];
}

const rngPrimary = range("primaryPLN");
const rngRent    = range("primeRentEUR");
const rngVac     = range("vac");
const rngYield   = range("yield");

function ThesisScreener() {
  const [thesis, setThesis] = useState<keyof typeof THESES>("resi_dev");
  const t = THESES[thesis];
  const invertSet = new Set(["vac", "yield"]);

  function norm(key: string, invert: boolean): number[] {
    const vals: number[] = dzielnice.map(d => {
      const dk = d as unknown as Record<string, number | string>;
      return key === "liquidity" ? liqScore(dk[key] as string) : (dk[key] as number);
    });
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const r = mx - mn || 1;
    return vals.map(v => {
      const n = (v - mn) / r;
      return invert ? 1 - n : n;
    });
  }

  const scored = dzielnice.map((d, idx) => {
    let s = 0;
    Object.entries(t.weights).forEach(([k, w]) => {
      const inv = invertSet.has(k);
      const arr = norm(k, inv);
      const v = arr[idx] ?? 0;
      s += (w >= 0 ? v : (1 - v)) * Math.abs(w);
    });
    return { ...d, score: s };
  }).sort((a, b) => b.score - a.score);

  const maxScore = Math.max(...scored.map(s => s.score));
  const fmtPct = (v: number) => Math.round(v * 100 / maxScore);

  return (
    <div className="ws-card" style={{ padding: 24, marginBottom: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18, gap: 24 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>Thesis screener</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>{t.blurb}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 300 }}>
          <div className="ws-upper" style={{ fontSize: 10, color: "var(--text-secondary)" }}>Investment thesis</div>
          <select value={thesis} onChange={e => setThesis(e.target.value as keyof typeof THESES)} style={{
            padding: "8px 10px", border: "1px solid var(--border)", background: "#fff",
            fontFamily: "inherit", fontSize: 13, color: "var(--text-primary)", cursor: "pointer",
          }}>
            {Object.entries(THESES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
      </div>

      <div style={{ borderTop: "1px solid var(--divider)", paddingTop: 18 }}>
        <div style={{ display: "grid", gridTemplateColumns: "40px 1fr 80px 1fr 240px", gap: 14, alignItems: "center", fontSize: 11, color: "var(--text-secondary)", paddingBottom: 8, borderBottom: "1px solid var(--divider)" }}>
          <div className="ws-upper">Rank</div>
          <div className="ws-upper">District</div>
          <div className="ws-upper" style={{ textAlign: "right" }}>Score</div>
          <div />
          <div className="ws-upper">Key signals</div>
        </div>
        {scored.map((d, i) => (
          <div key={d.n} style={{ display: "grid", gridTemplateColumns: "40px 1fr 80px 1fr 240px", gap: 14, alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--divider)" }}>
            <div className="mono tnum" style={{ fontSize: 13, color: i < 3 ? "var(--brand-navy)" : "var(--text-tertiary)", fontWeight: i < 3 ? 500 : 400 }}>
              {String(i + 1).padStart(2, "0")}
            </div>
            <div style={{ fontSize: 13, fontWeight: i < 3 ? 500 : 400 }}>{d.n}</div>
            <div className="tnum" style={{ textAlign: "right", fontSize: 13, fontWeight: 500 }}>{fmtPct(d.score)}</div>
            <div style={{ height: 6, background: "#F0F0F0", position: "relative" }}>
              <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${fmtPct(d.score)}%`, background: i < 3 ? "var(--brand-navy)" : "rgba(0,32,96,0.45)" }} />
            </div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", display: "flex", gap: 10, flexWrap: "wrap" }}>
              <span>YoY <span className="tnum" style={{ color: "var(--up)" }}>+{d.yoy.toFixed(1)}%</span></span>
              <span>Vac <span className="tnum">{d.vac.toFixed(1)}%</span></span>
              <span>Yld <span className="tnum">{d.yield.toFixed(2)}%</span></span>
              <span className="mono" style={{ color: "var(--text-tertiary)" }}>{d.liquidity}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 18, fontSize: 11, color: "var(--text-tertiary)", lineHeight: 1.5, fontStyle: "italic" }}>
        Scoring is rank-normalised within Warsaw — a top score reflects relative fit, not absolute attractiveness. Use as a screening prompt, not a recommendation.
      </div>
    </div>
  );
}

export function SubmarketsPage() {
  const [sortKey, setSortKey] = useState<SortKey>("primaryPLN");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [view, setView] = useState<"table" | "heat" | "compare" | "thesis">("table");

  const sorted = [...dzielnice].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (typeof av === "string") return sortDir === "asc" ? (av as string).localeCompare(bv as string) : (bv as string).localeCompare(av as string);
    return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
  });

  function setSort(k: SortKey) {
    if (sortKey === k) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  }

  function Th({ k, children, num }: { k: SortKey; children: React.ReactNode; num?: boolean }) {
    const arrow = sortKey === k ? (sortDir === "asc" ? " ↑" : " ↓") : "";
    return (
      <th
        className={num ? "num" : ""}
        onClick={() => setSort(k)}
        style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
      >
        {children}{arrow && <span style={{ fontSize: 9, color: "var(--brand-navy)" }}>{arrow}</span>}
      </th>
    );
  }

  const heatSpecs = [
    { key: "primaryPLN" as SortKey,    title: "Primary residential price", unit: "PLN/m²",   fmt: (v: number) => v.toLocaleString(),        rng: rngPrimary,    invert: false },
    { key: "primeRentEUR" as SortKey,  title: "Prime office rent",         unit: "€/m²/mo",  fmt: (v: number) => v.toFixed(1),              rng: rngRent,       invert: false },
    { key: "yoy" as SortKey,           title: "YoY price change",          unit: "%",         fmt: (v: number) => "+" + v.toFixed(1),        rng: [4, 20] as [number, number], invert: false },
    { key: "vac" as SortKey,           title: "Office vacancy",            unit: "%",         fmt: (v: number) => v.toFixed(1),              rng: rngVac,        invert: true  },
    { key: "yield" as SortKey,         title: "Prime office yield",        unit: "%",         fmt: (v: number) => v.toFixed(2),              rng: rngYield,      invert: true  },
    { key: "pipelineKsqm" as SortKey,  title: "Office pipeline",           unit: "k sqm",     fmt: (v: number) => v.toString(),              rng: [0, 250] as [number, number], invert: false },
  ];

  const compareRows: [string, (d: Dzielnica) => string][] = [
    ["Population (k)",      d => (d.pop / 1000).toFixed(0)],
    ["Area (km²)",          d => d.area.toFixed(1)],
    ["Primary PLN/m²",      d => d.primaryPLN.toLocaleString()],
    ["YoY %",               d => "+" + d.yoy.toFixed(1) + "%"],
    ["Prime rent €",        d => d.primeRentEUR.toFixed(2)],
    ["Vacancy %",           d => d.vac.toFixed(1) + "%"],
    ["Yield %",             d => d.yield.toFixed(2) + "%"],
    ["Net absorp. (k sqm)", d => d.absorpKsqm.toFixed(1)],
    ["Pipeline (k sqm)",    d => d.pipelineKsqm.toString()],
    ["Liquidity",           d => d.liquidity],
    ["Footfall",            d => d.footfall],
  ];

  return (
    <div style={{ overflowY: "auto", flex: 1 }}>
      <div style={{ padding: "32px 48px 48px", maxWidth: 1600, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
          <h1 className="ws-page-title">Submarkets</h1>
          <div className="tnum" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            18 dzielnice · last refresh <span className="mono">14 Apr 2026 06:08 CEST</span>
          </div>
        </div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 28 }}>
          Side-by-side comparison of Warsaw's 18 districts across residential, office and capital-markets metrics.
        </div>

        {/* View switcher + filters */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <div style={{ display: "flex", border: "1px solid var(--border)", overflow: "hidden", fontSize: 12 }}>
            {(["table", "heat", "compare", "thesis"] as const).map((k, i, arr) => (
              <button
                key={k}
                onClick={() => setView(k)}
                style={{
                  padding: "7px 14px", border: "none", cursor: "pointer",
                  background: view === k ? "var(--brand-navy)" : "#fff",
                  color: view === k ? "#fff" : "var(--text-secondary)",
                  fontFamily: "inherit", fontSize: 12,
                  borderRight: i < arr.length - 1 ? "1px solid var(--border)" : "none",
                }}
              >
                {k === "table" ? "Table" : k === "heat" ? "Heatmap" : k === "compare" ? "Compare" : "Thesis screener"}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {["All districts (18)", "Office tier ≥ A", "Residential active", "Export CSV"].map(l => (
              <span key={l} className="chip">{l}</span>
            ))}
          </div>
        </div>

        {/* Table view */}
        {view === "table" && (
          <div className="ws-card" style={{ padding: 0, marginBottom: 32, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="ws-table">
                <thead>
                  <tr>
                    <Th k="n">District</Th>
                    <Th k="pop" num>Pop. (k)</Th>
                    <Th k="area" num>Area km²</Th>
                    <Th k="primaryPLN" num>Primary PLN/m²</Th>
                    <Th k="yoy" num>YoY %</Th>
                    <Th k="primeRentEUR" num>Prime rent €</Th>
                    <Th k="vac" num>Vac. %</Th>
                    <Th k="yield" num>Yield %</Th>
                    <Th k="absorpKsqm" num>Absorp. k sqm</Th>
                    <Th k="pipelineKsqm" num>Pipeline k sqm</Th>
                    <Th k="liquidity">Liquidity</Th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(d => (
                    <tr key={d.n}>
                      <td style={{ fontWeight: 500 }}>{d.n}</td>
                      <td className="num">{(d.pop / 1000).toFixed(0)}</td>
                      <td className="num">{d.area.toFixed(1)}</td>
                      <td className="num" style={{ background: heatBg(d.primaryPLN, rngPrimary[0], rngPrimary[1]) }}>
                        {d.primaryPLN.toLocaleString()}
                      </td>
                      <td className="num" style={{ color: d.yoy >= 10 ? "var(--up)" : d.yoy >= 6 ? "var(--text-primary)" : "var(--text-secondary)" }}>
                        +{d.yoy.toFixed(1)}%
                      </td>
                      <td className="num" style={{ background: heatBg(d.primeRentEUR, rngRent[0], rngRent[1]) }}>
                        {d.primeRentEUR.toFixed(2)}
                      </td>
                      <td className="num" style={{ color: d.vac <= 8 ? "var(--up)" : d.vac >= 14 ? "var(--down)" : "var(--text-primary)" }}>
                        {d.vac.toFixed(1)}
                      </td>
                      <td className="num">{d.yield.toFixed(2)}</td>
                      <td className="num">{d.absorpKsqm.toFixed(1)}</td>
                      <td className="num" style={{ background: heatBg(d.pipelineKsqm, 0, 250) }}>{d.pipelineKsqm}</td>
                      <td className="mono" style={{ fontSize: 12, color: d.liquidity.startsWith("A") ? "var(--text-primary)" : "var(--text-secondary)" }}>
                        {d.liquidity}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "12px 20px", display: "flex", justifyContent: "space-between", borderTop: "1px solid var(--divider)", fontSize: 11, color: "var(--text-secondary)" }}>
              <div>Showing all 18 districts</div>
              <div style={{ color: "var(--text-tertiary)" }}>Heatmap shading: navy intensity = relative magnitude within column</div>
            </div>
          </div>
        )}

        {/* Heatmap view */}
        {view === "heat" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24, marginBottom: 32 }}>
            {heatSpecs.map(spec => (
              <div key={spec.key} className="ws-card" style={{ padding: "18px 20px" }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{spec.title}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 14 }}>{spec.unit}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4 }}>
                  {dzielnice.map(d => (
                    <div key={d.n} style={{
                      background: spec.invert
                        ? heatBgInv(d[spec.key] as number, spec.rng[0], spec.rng[1])
                        : heatBg(d[spec.key] as number, spec.rng[0], spec.rng[1]),
                      border: "1px solid var(--border)",
                      padding: "8px 10px", minHeight: 54,
                    }}>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.1 }}>{d.n}</div>
                      <div className="tnum" style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{spec.fmt(d[spec.key] as number)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Compare view */}
        {view === "compare" && (
          <div className="ws-card" style={{ padding: 24, marginBottom: 32 }}>
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Selected districts — peer comparison</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 18 }}>
              Sample: Wola, Centrum, Mokotów, Praga-Północ.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "160px repeat(4, 1fr)", gap: 0, fontSize: 13 }}>
              <div />
              {COMPARE_DISTRICTS.map(n => (
                <div key={n} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", fontSize: 14, fontWeight: 500 }}>{n}</div>
              ))}
              {compareRows.map(([label, get], ri) => (
                <>
                  <div key={"l" + ri} style={{ padding: "12px 14px", borderBottom: "1px solid var(--divider)", fontSize: 12, color: "var(--text-secondary)" }}>{label}</div>
                  {COMPARE_DISTRICTS.map(n => {
                    const d = dzielnice.find(x => x.n === n)!;
                    return (
                      <div key={n} className="tnum" style={{ padding: "12px 14px", borderBottom: "1px solid var(--divider)" }}>
                        {get(d)}
                      </div>
                    );
                  })}
                </>
              ))}
            </div>
          </div>
        )}

        {/* Thesis screener */}
        {view === "thesis" && <ThesisScreener />}

        {/* Methodology footer */}
        <div style={{ borderTop: "1px solid var(--divider)", paddingTop: 16, fontSize: 11, color: "var(--text-secondary)", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
          <div>
            <div className="ws-upper" style={{ marginBottom: 4 }}>Sources</div>
            MRiT Jawność · GUS BDL · NBP · GUGiK · JLL · CBRE · Cushman & Wakefield · Walter Herz
          </div>
          <div>
            <div className="ws-upper" style={{ marginBottom: 4 }}>Methodology</div>
            Primary residential prices are 30-day medians from Jawność cen mieszkań feed (developers ≥3 active investments). Office metrics quarterly snapshots.
          </div>
          <div>
            <div className="ws-upper" style={{ marginBottom: 4 }}>Liquidity rating</div>
            AAA = ≥4 transactions/year ≥€50m. Down to B = no comp transactions in 24 months.
          </div>
        </div>
      </div>
    </div>
  );
}
