// Primary Residential Market — Jawność cen mieszkań (developer pricing transparency)

import { useEffect, useState } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Summary {
  median_m2: number | null;
  active_units: number;
  last_updated: string | null;
  feed_lag_seconds: number | null;
  price_moves_7d: { up: number; dn: number };
}

interface LeaderboardRow {
  firm_name: string;
  initials: string;
  investments: number;
  active_units: number;
  median_m2: number | null;
  districts: string[];
}

interface HeatmapRow {
  district: string;
  median_m2: number | null;
  unit_count: number;
}

interface PriceChange {
  change_date: string | null;
  firm_name: string;
  initials: string;
  investment_name: string;
  district: string | null;
  prev_m2: number | null;
  curr_m2: number | null;
  dpct: number;
  unit_count: number;
  dir: "up" | "down";
}

interface PipelineRow {
  district: string;
  available_units: number;
  reserved_units: number;
  total_units: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtLag(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 120) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pl-PL", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function DistHeatmap({ data }: { data: HeatmapRow[] }) {
  if (!data.length) return <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: 16 }}>No district data yet.</div>;
  const vals = data.map(d => d.median_m2 ?? 0).filter(v => v > 0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  function blend(v: number) {
    const t = max > min ? (v - min) / (max - min) : 0.5;
    const r = Math.round(220 + t * (0 - 220));
    const g = Math.round(230 + t * (32 - 230));
    const b = Math.round(242 + t * (96 - 242));
    return `rgb(${r},${g},${b})`;
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4 }}>
      {data.map((d, i) => (
        <div key={i} style={{ background: blend(d.median_m2 ?? min), padding: "10px 12px" }}>
          <div style={{ fontSize: 11, fontWeight: 500, color: "var(--text-heading)" }}>{d.district}</div>
          <div className="tnum" style={{ fontSize: 16, fontWeight: 600, color: "var(--brand-navy)", marginTop: 2 }}>
            {(d.median_m2 ?? 0).toLocaleString("pl-PL")}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>PLN/m² · {d.unit_count} units</div>
        </div>
      ))}
    </div>
  );
}

function PipelineChart({ data }: { data: PipelineRow[] }) {
  if (!data.length) return <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: 16 }}>No pipeline data yet.</div>;
  const W = 640, H = 240, pad = { l: 90, r: 20, t: 16, b: 28 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const maxV = Math.max(...data.map(d => d.total_units), 1);
  const items = data.slice(0, 11);
  const bH = ih / items.length - 3;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {items.map((d, i) => {
        const y = pad.t + i * (ih / items.length) + 1;
        const xAvail = (d.available_units / maxV) * iw;
        const xReserved = (d.reserved_units / maxV) * iw;
        return (
          <g key={i}>
            <text x={pad.l - 6} y={y + bH * 0.65} fontSize="10" fill="#525252" textAnchor="end" fontFamily="IBM Plex Sans">{d.district}</text>
            <rect x={pad.l} y={y + bH * 0.05} width={xAvail} height={bH * 0.45} fill="#002060" />
            <rect x={pad.l} y={y + bH * 0.55} width={xReserved} height={bH * 0.4} fill="#DCE6F2" />
          </g>
        );
      })}
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={H - pad.b} stroke="#A3A3A3" />
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#A3A3A3" />
      {[0, Math.round(maxV * 0.25), Math.round(maxV * 0.5), Math.round(maxV * 0.75), maxV].map(v => (
        <text key={v} x={pad.l + (v / maxV) * iw} y={H - pad.b + 12} fontSize="9" fill="#525252" fontFamily="IBM Plex Sans" textAnchor="middle">{v}</text>
      ))}
      {[{ c: "#002060", l: "Available" }, { c: "#DCE6F2", l: "Reserved" }].map((leg, i) => (
        <g key={i}>
          <rect x={W - pad.r - 140 + i * 70} y={pad.t - 2} width={10} height={8} fill={leg.c} />
          <text x={W - pad.r - 128 + i * 70} y={pad.t + 5} fontSize="9" fill="#525252" fontFamily="IBM Plex Sans">{leg.l}</text>
        </g>
      ))}
    </svg>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export function PrimaryMarketPage() {
  const [feedDays, setFeedDays] = useState(7);

  const [summary, setSummary] = useState<Summary | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapRow[]>([]);
  const [priceChanges, setPriceChanges] = useState<PriceChange[]>([]);
  const [pipeline, setPipeline] = useState<PipelineRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch("/api/primary-market/summary").then(r => r.json()),
      fetch("/api/primary-market/leaderboard").then(r => r.json()),
      fetch("/api/primary-market/heatmap").then(r => r.json()),
      fetch("/api/primary-market/pipeline").then(r => r.json()),
    ]).then(([s, l, h, p]) => {
      setSummary(s);
      setLeaderboard(l);
      setHeatmap(h);
      setPipeline(p);
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetch(`/api/primary-market/price-changes?days=${feedDays}`)
      .then(r => r.json())
      .then(setPriceChanges)
      .catch(console.error);
  }, [feedDays]);

  const isLive = summary?.feed_lag_seconds != null && summary.feed_lag_seconds < 7200;
  const totalMoves = (summary?.price_moves_7d.up ?? 0) + (summary?.price_moves_7d.dn ?? 0);
  const upPct = totalMoves > 0 ? Math.round((summary!.price_moves_7d.up / totalMoves) * 100) : 0;

  const heatmapMin = Math.min(...heatmap.map(d => d.median_m2 ?? 0).filter(v => v > 0));
  const heatmapMax = Math.max(...heatmap.map(d => d.median_m2 ?? 0));

  return (
    <div style={{ padding: "32px 48px 48px", maxWidth: 1600, margin: "0 auto", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
        <h1 className="ws-page-title">Primary Residential Market</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--text-secondary)" }}>
          {isLive && (
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%", background: "#22c55e",
                boxShadow: "0 0 0 2px rgba(34,197,94,0.25)",
                animation: "pulse 2s infinite",
                display: "inline-block",
              }} />
              <span style={{ color: "#22c55e", fontWeight: 500 }}>LIVE</span>
            </span>
          )}
          <span className="tnum">
            Jawność cen mieszkań · lag{" "}
            <span className="mono">{fmtLag(summary?.feed_lag_seconds ?? null)}</span>
            {" · last sync "}
            <span className="mono">{fmtDate(summary?.last_updated ?? null)}</span>
          </span>
        </div>
      </div>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 32 }}>
        Developer pricing from the statutory MRiT Jawność cen mieszkań feed — 15-minute cadence · {leaderboard.length} firms · {heatmap.length} dzielnice.
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 48 }}>
        <div className="kpi-card">
          <div className="label">Warsaw median PLN/m²</div>
          <div className="value tnum" style={{ marginTop: 8 }}>
            {loading ? "…" : (summary?.median_m2?.toLocaleString("pl-PL") ?? "—")}
          </div>
          <div className="delta up" style={{ marginTop: 8 }}>
            <span>▲</span> <span className="tnum">WSRE composite</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--divider)" }}>
            All active units · Jawność feed
          </div>
        </div>
        <div className="kpi-card">
          <div className="label">Active listings</div>
          <div className="value tnum" style={{ marginTop: 8 }}>
            {loading ? "…" : (summary?.active_units?.toLocaleString("pl-PL") ?? "—")}
          </div>
          <div className="delta up" style={{ marginTop: 8 }}>
            <span>▲</span> <span className="tnum">status: wolne</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--divider)" }}>
            Jawność feed
          </div>
        </div>
        <div className="kpi-card">
          <div className="label">Price moves (7d ▲)</div>
          <div className="value tnum" style={{ marginTop: 8 }}>
            {loading ? "…" : `${upPct}%`}<span className="unit"> ▲</span>
          </div>
          <div className="delta up" style={{ marginTop: 8 }}>
            <span>▲</span>{" "}
            <span className="tnum">
              {totalMoves > 0 ? Math.round((summary!.price_moves_7d.dn / totalMoves) * 100) : 0}% cuts
            </span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--divider)" }}>
            {summary?.price_moves_7d.up ?? 0} ▲ · {summary?.price_moves_7d.dn ?? 0} ▼
          </div>
        </div>
        <div className="kpi-card">
          <div className="label">Feed lag</div>
          <div className="value tnum mono" style={{ marginTop: 8, fontSize: 28 }}>
            {loading ? "…" : fmtLag(summary?.feed_lag_seconds ?? null)}
          </div>
          <div className={`delta ${isLive ? "up" : "dn"}`} style={{ marginTop: 8 }}>
            <span>{isLive ? "▲" : "▼"}</span>{" "}
            <span className="tnum">{isLive ? "feed active" : "feed stale"}</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--divider)" }}>
            Time since last ingest run
          </div>
        </div>
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
              <th>Primary markets</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-secondary)", padding: 24 }}>Loading…</td></tr>
            ) : leaderboard.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-secondary)", padding: 24 }}>No data ingested yet.</td></tr>
            ) : leaderboard.map((d, i) => (
              <tr key={i}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{
                      width: 32, height: 32, background: "#fff", border: "1px solid var(--border)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 11, fontWeight: 600, color: "var(--text-heading)", fontFamily: "IBM Plex Mono",
                    }}>{d.initials}</div>
                    <span style={{ fontWeight: 500 }}>{d.firm_name}</span>
                  </div>
                </td>
                <td className="num">{d.investments}</td>
                <td className="num">{d.active_units.toLocaleString("pl-PL")}</td>
                <td className="num" style={{ fontWeight: 500 }}>
                  {d.median_m2?.toLocaleString("pl-PL") ?? "—"}
                </td>
                <td style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  {d.districts.join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ padding: "12px 20px", fontSize: 11, color: "var(--text-secondary)" }}>
          Source: MRiT · Jawność cen mieszkań · {fmtDate(summary?.last_updated ?? null)}
        </div>
      </div>

      {/* District heatmap */}
      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>District Price Heatmap</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ marginBottom: 48 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>Median asking price by dzielnica — all active listings</div>
          {heatmap.length > 0 && (
            <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
              Range: {heatmapMin.toLocaleString("pl-PL")} – {heatmapMax.toLocaleString("pl-PL")} PLN/m²
            </div>
          )}
        </div>
        {loading ? (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: "16px 0" }}>Loading…</div>
        ) : (
          <DistHeatmap data={heatmap} />
        )}
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 12 }}>
          Source: MRiT · Jawność cen mieszkań · WSRE composite · {fmtDate(summary?.last_updated ?? null)}
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
              <th>Date</th><th>Developer</th><th>Investment</th><th>District</th>
              <th className="num">Before</th><th className="num">After</th><th className="num">Δ%</th><th className="num">Units</th>
            </tr>
          </thead>
          <tbody>
            {priceChanges.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-secondary)", padding: 24 }}>
                No price changes in the last {feedDays} day{feedDays !== 1 ? "s" : ""}.
              </td></tr>
            ) : priceChanges.map((p, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                  {p.change_date ?? "—"}
                </td>
                <td style={{ fontSize: 12, color: "var(--text-secondary)" }}>{p.firm_name}</td>
                <td style={{ fontSize: 12 }}>{p.investment_name}</td>
                <td style={{ fontSize: 12, color: "var(--text-secondary)" }}>{p.district ?? "—"}</td>
                <td className="num" style={{ fontSize: 12 }}>
                  {p.prev_m2?.toLocaleString("pl-PL") ?? "—"}
                </td>
                <td className="num" style={{ fontSize: 12, fontWeight: 500 }}>
                  {p.curr_m2?.toLocaleString("pl-PL") ?? "—"}
                </td>
                <td className="num" style={{ color: p.dir === "up" ? "var(--up)" : "var(--down)", fontWeight: 500 }}>
                  {p.dpct >= 0 ? "+" : ""}{p.dpct.toFixed(2)}%
                </td>
                <td className="num">{p.unit_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Supply pipeline */}
      <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-heading)", margin: "0 0 14px" }}>Supply Pipeline</h2>
      <div style={{ borderTop: "1px solid var(--divider)", marginBottom: 20 }} />
      <div className="ws-card" style={{ marginBottom: 48 }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Active + reserved units by district</div>
        {loading ? (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: "16px 0" }}>Loading…</div>
        ) : (
          <PipelineChart data={pipeline} />
        )}
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
          Source: Jawność feed · {fmtDate(summary?.last_updated ?? null)}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>

      <div style={{ marginTop: 64, paddingTop: 20, borderTop: "1px solid var(--divider)", fontSize: 11, color: "var(--text-tertiary)", display: "flex", justifyContent: "space-between" }}>
        <span>Strictly private &amp; confidential · WSRE Intelligence · Prepared for internal circulation and select partners</span>
        <span className="tnum mono">v0.5.0 · {new Date().toLocaleDateString("pl-PL")}</span>
      </div>
    </div>
  );
}
