/**
 * SubmarketsPage — district comparison and choropleth overview.
 *
 * Route: /submarkets
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

interface DistrictRow {
  district_key: string;
  name_en: string;
  name_ar: string | null;
  tx_count: number;
  avg_price_per_sqm: number | null;
  latest_month: string | null;
}

function useDistrictSummary() {
  return useQuery<DistrictRow[]>({
    queryKey: ["district-velocity-summary"],
    queryFn: () => api.get<DistrictRow[]>("/api/spatial/district-velocity?window_days=365&limit=20"),
  });
}

function fmt(v: number | null, digits = 0): string {
  if (v == null) return "—";
  return v.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function SubmarketsPage() {
  const { data: rows = [], isLoading } = useDistrictSummary();

  return (
    <div style={{ flex: 1, overflowY: "auto", background: "var(--bg-page)" }}>
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "32px 32px 64px" }}>

        {/* Page heading */}
        <div style={{ marginBottom: "24px" }}>
          <h1 className="ws-page-title">Submarkets</h1>
          <p className="ws-meta" style={{ marginTop: "6px" }}>
            Transaction velocity and pricing by district · 12-month lookback
          </p>
        </div>

        {/* District comparison table */}
        <div className="ws-card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{
            padding: "14px 20px", borderBottom: "1px solid var(--border)",
            fontSize: "11px", fontWeight: 500, textTransform: "uppercase",
            letterSpacing: "0.5px", color: "var(--text-secondary)",
          }}>
            District Transaction Summary
          </div>

          {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

          {!isLoading && rows.length === 0 && (
            <div className="empty-state">No district data available. Run the velocity query.</div>
          )}

          {rows.length > 0 && (
            <table className="ws-table">
              <thead>
                <tr>
                  <th>District</th>
                  <th>Arabic</th>
                  <th className="num">Transactions</th>
                  <th className="num">Avg SAR / m²</th>
                  <th>Latest Month</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.district_key}>
                    <td style={{ fontWeight: 500 }}>{row.name_en}</td>
                    <td style={{ fontFamily: "'IBM Plex Sans Arabic', sans-serif", direction: "rtl" }}>
                      {row.name_ar ?? "—"}
                    </td>
                    <td className="num mono">{fmt(row.tx_count)}</td>
                    <td className="num mono">{fmt(row.avg_price_per_sqm, 0)}</td>
                    <td className="mono" style={{ color: "var(--text-secondary)", fontSize: "12px" }}>
                      {row.latest_month ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <p style={{ marginTop: "16px", fontSize: "12px", color: "var(--text-tertiary)" }}>
          Choropleth map view coming soon. Use the Workbench to explore district polygons spatially.
        </p>
      </div>
    </div>
  );
}
