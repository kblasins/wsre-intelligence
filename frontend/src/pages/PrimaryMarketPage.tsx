// Primary Residential Market — Jawność cen mieszkań (developer pricing transparency)

import { useState } from "react";

const developers = [
  { logo: "DD", name: "Dom Development",  inv: 21, units: 3840, medPLN: 18900, mom:  0.6, yoy:  9.4, up: 14, dn: 3, primary: ["Mokotów","Wola","Wilanów"] },
  { logo: "AT", name: "Atal",             inv: 18, units: 3120, medPLN: 14800, mom:  0.4, yoy:  7.2, up: 11, dn: 5, primary: ["Białołęka","Targówek","Bemowo"] },
  { logo: "EI", name: "Echo Investment",  inv: 14, units: 2680, medPLN: 17400, mom:  1.1, yoy: 11.8, up: 18, dn: 2, primary: ["Wola","Praga-Pn","Ursus"] },
  { logo: "RB", name: "Robyg",            inv: 16, units: 2540, medPLN: 16200, mom:  0.8, yoy:  9.6, up: 12, dn: 4, primary: ["Białołęka","Bemowo","Wilanów"] },
  { logo: "DV", name: "Develia",          inv: 11, units: 1860, medPLN: 15800, mom:  0.3, yoy:  6.8, up:  9, dn: 6, primary: ["Mokotów","Ursynów"] },
  { logo: "MV", name: "Marvipol",         inv:  9, units: 1240, medPLN: 19400, mom:  0.9, yoy: 10.4, up:  8, dn: 1, primary: ["Mokotów","Wola"] },
  { logo: "OK", name: "Okam",             inv:  8, units: 1080, medPLN: 14600, mom:  1.4, yoy: 13.6, up: 11, dn: 0, primary: ["Praga-Pn","Targówek"] },
  { logo: "YT", name: "Yit Polska",       inv:  7, units:  940, medPLN: 16800, mom:  0.5, yoy:  8.2, up:  6, dn: 3, primary: ["Bielany","Żoliborz"] },
  { logo: "VS", name: "Victoria Dom",     inv:  7, units:  880, medPLN: 13900, mom:  0.2, yoy:  5.8, up:  5, dn: 4, primary: ["Białołęka","Wawer"] },
  { logo: "AC", name: "Archicom",         inv:  6, units:  720, medPLN: 15400, mom:  0.7, yoy:  8.8, up:  7, dn: 2, primary: ["Mokotów","Wilanów"] },
  { logo: "MT", name: "Matexi",           inv:  5, units:  580, medPLN: 18200, mom:  1.0, yoy: 10.6, up:  6, dn: 1, primary: ["Wola","Śródmieście"] },
  { logo: "BD", name: "Budimex Nieruch.", inv:  6, units:  640, medPLN: 15600, mom:  0.4, yoy:  7.4, up:  5, dn: 3, primary: ["Bielany","Bemowo"] },
];

const distPrices = [
  { n: "Śródmieście",    v: 24800, units:  320, devs:  8 },
  { n: "Wola",           v: 21900, units: 1240, devs: 14 },
  { n: "Żoliborz",       v: 18800, units:  380, devs:  6 },
  { n: "Mokotów",        v: 18400, units: 1860, devs: 18 },
  { n: "Wilanów",        v: 18200, units:  740, devs:  9 },
  { n: "Ochota",         v: 19200, units:  240, devs:  5 },
  { n: "Praga-Północ",   v: 16800, units:  920, devs: 11 },
  { n: "Ursynów",        v: 16400, units:  480, devs:  7 },
  { n: "Praga-Południe", v: 15600, units:  680, devs:  9 },
  { n: "Włochy",         v: 14600, units:  320, devs:  6 },
  { n: "Bemowo",         v: 14200, units:  740, devs:  9 },
  { n: "Bielany",        v: 14800, units:  460, devs:  7 },
  { n: "Ursus",          v: 13800, units:  540, devs:  7 },
  { n: "Targówek",       v: 13800, units:  620, devs:  8 },
  { n: "Wawer",          v: 13600, units:  280, devs:  5 },
  { n: "Białołęka",      v: 13400, units: 1180, devs: 12 },
  { n: "Wesoła",         v: 12800, units:   80, devs:  3 },
  { n: "Rembertów",      v: 12400, units:  120, devs:  4 },
];

const priceChanges = [
  { ts: "14 Apr 06:04", dev: "Echo Investment",  inv: "Stacja Wola — etap III",       dist: "Wola",     pre: 21400, post: 21900, dpct:  2.34, units:  8, dir: "up"   },
  { ts: "14 Apr 05:48", dev: "Dom Development",  inv: "Mokotów Park — Bldg D",        dist: "Mokotów",  pre: 19200, post: 19500, dpct:  1.56, units: 14, dir: "up"   },
  { ts: "14 Apr 05:31", dev: "Atal",             inv: "Nowa Białołęka — etap V",      dist: "Białołęka",pre: 13800, post: 14000, dpct:  1.45, units: 22, dir: "up"   },
  { ts: "14 Apr 02:12", dev: "Marvipol",         inv: "Unisono Wola",                 dist: "Wola",     pre: 22400, post: 22900, dpct:  2.23, units:  6, dir: "up"   },
  { ts: "13 Apr 22:40", dev: "Okam",             inv: "Praga Heart — etap II",        dist: "Praga-Pn", pre: 14600, post: 14400, dpct: -1.37, units:  4, dir: "down" },
  { ts: "13 Apr 19:18", dev: "Robyg",            inv: "Bemowo Sky",                   dist: "Bemowo",   pre: 15800, post: 16100, dpct:  1.90, units: 11, dir: "up"   },
  { ts: "13 Apr 16:02", dev: "Victoria Dom",     inv: "Osiedle Bliska Wola",          dist: "Wola",     pre: 18900, post: 19200, dpct:  1.59, units:  9, dir: "up"   },
  { ts: "13 Apr 13:45", dev: "Develia",          inv: "Ceglana Park",                 dist: "Mokotów",  pre: 17800, post: 17600, dpct: -1.12, units:  3, dir: "down" },
  { ts: "13 Apr 11:22", dev: "Yit Polska",       inv: "Aroma Park — etap II",         dist: "Bielany",  pre: 16400, post: 16700, dpct:  1.83, units: 18, dir: "up"   },
  { ts: "12 Apr 21:36", dev: "Budimex Nieruch.", inv: "Bielany Residence",            dist: "Bielany",  pre: 15200, post: 15400, dpct:  1.32, units:  9, dir: "up"   },
  { ts: "12 Apr 17:20", dev: "Echo Investment",  inv: "Browary Warszawskie — etap VI",dist: "Wola",     pre: 24400, post: 24800, dpct:  1.64, units:  4, dir: "up"   },
];

const pipeline = [
  { dist: "Białołęka", y2026:  920, y2027: 1320, y2028:  480 },
  { dist: "Wola",      y2026:  740, y2027:  980, y2028:  360 },
  { dist: "Mokotów",   y2026:  680, y2027:  920, y2028:  240 },
  { dist: "Praga-Pd",  y2026:  540, y2027:  720, y2028:  180 },
  { dist: "Targówek",  y2026:  380, y2027:  540, y2028:  160 },
  { dist: "Bemowo",    y2026:  360, y2027:  480, y2028:  220 },
  { dist: "Ursus",     y2026:  320, y2027:  460, y2028:  140 },
  { dist: "Wilanów",   y2026:  280, y2027:  420, y2028:  180 },
  { dist: "Bielany",   y2026:  240, y2027:  280, y2028:  120 },
  { dist: "Ursynów",   y2026:  180, y2027:  240, y2028:   80 },
  { dist: "Włochy",    y2026:  160, y2027:  220, y2028:   60 },
];

function DistHeatmap() {
  const min = Math.min(...distPrices.map(d => d.v));
  const max = Math.max(...distPrices.map(d => d.v));
  function blend(v: number) {
    const t = (v - min) / (max - min);
    const r = Math.round(220 + t * (0 - 220));
    const g = Math.round(230 + t * (32 - 230));
    const b = Math.round(242 + t * (96 - 242));
    return `rgb(${r},${g},${b})`;
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4 }}>
      {distPrices.map((d, i) => (
        <div key={i} style={{ background: blend(d.v), padding: "10px 12px" }}>
          <div style={{ fontSize: 11, fontWeight: 500, color: "var(--text-heading)" }}>{d.n}</div>
          <div className="tnum" style={{ fontSize: 16, fontWeight: 600, color: "var(--brand-navy)", marginTop: 2 }}>
            {d.v.toLocaleString("pl-PL")}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>PLN/m² · {d.units} units</div>
        </div>
      ))}
    </div>
  );
}

function PipelineChart() {
  const W = 640, H = 240, pad = { l: 80, r: 20, t: 16, b: 28 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const maxV = 2400;
  const bH = ih / pipeline.length - 3;
  const colors = { y2026: "#002060", y2027: "#2D358A", y2028: "#DCE6F2" };
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {pipeline.map((d, i) => {
        const y = pad.t + i * (ih / pipeline.length) + 1;
        const x2026 = (d.y2026 / maxV) * iw;
        const x2027 = (d.y2027 / maxV) * iw;
        const x2028 = (d.y2028 / maxV) * iw;
        return (
          <g key={i}>
            <text x={pad.l - 6} y={y + bH * 0.6} fontSize="10" fill="#525252" textAnchor="end" fontFamily="IBM Plex Sans">{d.dist}</text>
            <rect x={pad.l} y={y} width={x2026} height={bH * 0.3} fill={colors.y2026} />
            <rect x={pad.l} y={y + bH * 0.35} width={x2027} height={bH * 0.3} fill={colors.y2027} />
            <rect x={pad.l} y={y + bH * 0.7} width={x2028} height={bH * 0.3} fill={colors.y2028} />
          </g>
        );
      })}
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={H - pad.b} stroke="#A3A3A3" />
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#A3A3A3" />
      {[0, 500, 1000, 1500, 2000].map(v => (
        <text key={v} x={pad.l + (v / maxV) * iw} y={H - pad.b + 12} fontSize="9" fill="#525252" fontFamily="IBM Plex Sans" textAnchor="middle">{v}</text>
      ))}
      {/* Legend */}
      {[{ c: colors.y2026, l: "2026" }, { c: colors.y2027, l: "2027" }, { c: colors.y2028, l: "2028+" }].map((leg, i) => (
        <g key={i}>
          <rect x={W - pad.r - 120 + i * 40} y={pad.t - 2} width={10} height={8} fill={leg.c} />
          <text x={W - pad.r - 108 + i * 40} y={pad.t + 5} fontSize="9" fill="#525252" fontFamily="IBM Plex Sans">{leg.l}</text>
        </g>
      ))}
    </svg>
  );
}

export function PrimaryMarketPage() {
  const [feedDays, setFeedDays] = useState(3);

  return (
    <div style={{ padding: "32px 48px 48px", maxWidth: 1600, margin: "0 auto", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
        <h1 className="ws-page-title">Primary Residential Market</h1>
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }} className="tnum">
          Jawność cen mieszkań · last sync <span className="mono">14 Apr 2026 06:14 CEST</span>
        </div>
      </div>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 32 }}>
        Developer pricing from the statutory MRiT Jawność cen mieszkań feed — 15-minute cadence, 12 developers, 18 dzielnice.
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 48 }}>
        {[
          { l: "Warsaw avg PLN/m²", v: "16,420", u: "", ch: "+0.6% MoM", dir: "up", ft: "WSRE composite · 14 Apr 2026" },
          { l: "YoY change",        v: "+9.2",   u: "%", ch: "vs +6.8% last year", dir: "up", ft: "12-month rolling" },
          { l: "Active listings",   v: "18,640", u: "", ch: "+284 this week",     dir: "up", ft: "Jawność feed" },
          { l: "Price moves (7d)",  v: "79%",    u: "▲", ch: "21% cuts", dir: "up", ft: "142 ▲ · 38 ▼" },
        ].map((k, i) => (
          <div key={i} className="kpi-card">
            <div className="label">{k.l}</div>
            <div className="value tnum" style={{ marginTop: 8 }}>{k.v}<span className="unit">{k.u}</span></div>
            <div className={"delta " + k.dir} style={{ marginTop: 8 }}>
              <span>▲</span> <span className="tnum">{k.ch}</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--divider)" }}>{k.ft}</div>
          </div>
        ))}
      </div>

      {/* Developer leaderboard */}
      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Developer Leaderboard</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ padding: 0, marginBottom: 48 }}>
        <table className="ws-table">
          <thead>
            <tr>
              <th>Developer</th>
              <th className="num">Investments</th>
              <th className="num">Active units</th>
              <th className="num">Median PLN/m²</th>
              <th className="num">MoM</th>
              <th className="num">YoY</th>
              <th className="num">▲ / ▼ (30d)</th>
              <th>Primary markets</th>
            </tr>
          </thead>
          <tbody>
            {developers.map((d, i) => (
              <tr key={i}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{
                      width: 32, height: 32, background: "#fff", border: "1px solid var(--border)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 11, fontWeight: 600, color: "var(--text-heading)", fontFamily: "IBM Plex Mono",
                    }}>{d.logo}</div>
                    <span style={{ fontWeight: 500 }}>{d.name}</span>
                  </div>
                </td>
                <td className="num">{d.inv}</td>
                <td className="num">{d.units.toLocaleString("pl-PL")}</td>
                <td className="num" style={{ fontWeight: 500 }}>{d.medPLN.toLocaleString("pl-PL")}</td>
                <td className="num" style={{ color: d.mom >= 0 ? "var(--up)" : "var(--down)" }}>
                  {d.mom >= 0 ? "+" : ""}{d.mom.toFixed(1)}%
                </td>
                <td className="num" style={{ color: d.yoy >= 0 ? "var(--up)" : "var(--down)" }}>
                  {d.yoy >= 0 ? "+" : ""}{d.yoy.toFixed(1)}%
                </td>
                <td className="num">
                  <span style={{ color: "var(--up)" }}>{d.up}▲</span>
                  {" / "}
                  <span style={{ color: "var(--down)" }}>{d.dn}▼</span>
                </td>
                <td style={{ fontSize: 11, color: "var(--text-secondary)" }}>{d.primary.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ padding: "12px 20px", fontSize: 11, color: "var(--text-secondary)" }}>
          Source: MRiT · Jawność cen mieszkań · 14 Apr 2026
        </div>
      </div>

      {/* District heatmap */}
      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>District Price Heatmap</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ marginBottom: 48 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>Median asking price by dzielnica — all active listings</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Range: 12,400 – 24,800 PLN/m²</div>
        </div>
        <DistHeatmap />
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 12 }}>
          Source: MRiT · Jawność cen mieszkań · WSRE composite · 14 Apr 2026
        </div>
      </div>

      {/* Price change feed */}
      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Recent Price Changes</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ padding: 0, marginBottom: 48 }}>
        <div style={{ padding: "12px 16px 8px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--divider)" }}>
          <div style={{ fontSize: 12, fontWeight: 500 }}>Live price events — Jawność feed</div>
          <div style={{ display: "flex", gap: 6 }}>
            {[1, 3, 7].map(d => (
              <span key={d} className={"chip" + (feedDays === d ? " active" : "")} onClick={() => setFeedDays(d)}>{d}d</span>
            ))}
          </div>
        </div>
        <table className="ws-table">
          <thead>
            <tr>
              <th>Time</th><th>Developer</th><th>Investment</th><th>District</th>
              <th className="num">Before</th><th className="num">After</th><th className="num">Δ%</th><th className="num">Units</th>
            </tr>
          </thead>
          <tbody>
            {priceChanges.map((p, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{p.ts}</td>
                <td style={{ fontSize: 12, color: "var(--text-secondary)" }}>{p.dev}</td>
                <td style={{ fontSize: 12 }}>{p.inv}</td>
                <td style={{ fontSize: 12, color: "var(--text-secondary)" }}>{p.dist}</td>
                <td className="num" style={{ fontSize: 12 }}>{p.pre.toLocaleString("pl-PL")}</td>
                <td className="num" style={{ fontSize: 12, fontWeight: 500 }}>{p.post.toLocaleString("pl-PL")}</td>
                <td className="num" style={{ color: p.dir === "up" ? "var(--up)" : "var(--down)", fontWeight: 500 }}>
                  {p.dpct >= 0 ? "+" : ""}{p.dpct.toFixed(2)}%
                </td>
                <td className="num">{p.units}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Supply pipeline */}
      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Supply Pipeline</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ marginBottom: 48 }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Units expected by district — 2026–2028</div>
        <PipelineChart />
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
          Source: WSRE pipeline tracker · Jawność feed · 14 Apr 2026
        </div>
      </div>

      <div style={{ marginTop: 64, paddingTop: 20, borderTop: "1px solid var(--divider)", fontSize: 11, color: "var(--text-tertiary)", display: "flex", justifyContent: "space-between" }}>
        <span>Strictly private & confidential · WSRE Intelligence · Prepared for internal circulation and select partners</span>
        <span className="tnum mono">v0.4.2 · 14 Apr 2026</span>
      </div>
    </div>
  );
}
