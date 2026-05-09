import { useState } from "react";
import { useRentIndex } from "../hooks/useMarketData";
import type { RentIndexEntry } from "../types/api";
import { RentHeatmap } from "./charts/RentHeatmap";
import { RentTrendChart } from "./charts/RentTrendChart";
import { RentDistrictBarChart } from "./charts/RentDistrictBarChart";

const PTYPES = ["warehouse", "industrial_land", "factory", "logistics", "office", "retail"];

function fmt(n: number) {
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function fmtPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function sourceLabel(source: string) {
  if (source.startsWith("news_article_")) return "news";
  if (source.includes("knight_frank")) return "Knight Frank";
  if (source.includes("cbre")) return "CBRE";
  if (source.includes("jll")) return "JLL";
  if (source.includes("rega")) return "REGA";
  return source.replace(/_/g, " ");
}

function PriorityPill({ priority }: { priority: number }) {
  const label = ["", "REGA", "Report", "News", "Portal"][priority] ?? `P${priority}`;
  const cls = priority === 1 ? "macro" : priority === 2 ? "transaction" : "commentary";
  return <span className={`type-pill ${cls}`}>{label}</span>;
}

function groupByPeriod(entries: RentIndexEntry[]) {
  const map: Record<string, RentIndexEntry[]> = {};
  for (const e of entries) {
    (map[e.period] ??= []).push(e);
  }
  return Object.entries(map).sort((a, b) => b[0].localeCompare(a[0]));
}

export function RentIndexPanel() {
  const [selectedType, setSelectedType] = useState<string>("");
  const { data: entries, isLoading } = useRentIndex(selectedType || undefined);

  const periodGroups = groupByPeriod(entries ?? []);

  return (
    <div style={{ marginTop: "32px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid var(--border)",
      }}>
        <h3 className="ws-sub-h">Rent Index</h3>
        <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          {["", ...PTYPES].map(pt => (
            <button
              key={pt}
              className={`chip${selectedType === pt ? " active" : ""}`}
              onClick={() => setSelectedType(pt)}
              style={{ padding: "3px 8px", fontSize: "11px" }}
            >
              {pt || "All"}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

      {!isLoading && (entries?.length ?? 0) === 0 && (
        <div className="empty-state">
          <p style={{ marginBottom: "8px", fontWeight: 500 }}>No rent index data yet.</p>
          <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", color: "var(--brand-navy)" }}>
            make extract-pdf FILE=path/to/report.pdf
          </code>
          <p className="ws-small" style={{ maxWidth: "400px", lineHeight: 1.6, marginTop: "6px" }}>
            Upload Knight Frank / CBRE / JLL reports to populate the rent index.
          </p>
        </div>
      )}

      {entries && entries.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <RentHeatmap data={entries} />
          <RentDistrictBarChart data={entries} propertyType={selectedType || undefined} />
          <RentTrendChart data={entries} />

          {periodGroups.map(([period, rows]) => (
            <div key={period} className="ws-card" style={{ padding: 0, overflow: "hidden", animation: "fadeUp 0.4s ease both" }}>
              <div style={{
                padding: "10px 16px", borderBottom: "1px solid var(--border)",
                display: "flex", alignItems: "center", gap: "12px",
                background: "var(--bg-header)",
              }}>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "13px", fontWeight: 500, color: "var(--text-primary)" }}>
                  {period}
                </span>
                <span className="ws-small">
                  {rows.length} observation{rows.length !== 1 ? "s" : ""}
                </span>
              </div>

              <table className="ws-table">
                <thead>
                  <tr>
                    <th>District</th>
                    <th>Type</th>
                    <th className="num">SAR/sqm/yr</th>
                    <th className="num">YoY Δ</th>
                    <th className="num">Vacancy</th>
                    <th>Source</th>
                    <th>Priority</th>
                  </tr>
                </thead>
                <tbody>
                  {rows
                    .sort((a, b) => a.source_priority - b.source_priority)
                    .map((row) => (
                      <tr key={row.id}>
                        <td>{row.district ?? <span style={{ color: "var(--text-tertiary)" }}>—</span>}</td>
                        <td className="mono">{row.property_type.replace(/_/g, " ")}</td>
                        <td className="num">{row.rent_sar_sqm_annual != null ? fmt(row.rent_sar_sqm_annual) : "—"}</td>
                        <td className="num" style={{
                          color: row.yoy_change_pct == null ? "var(--text-tertiary)"
                            : row.yoy_change_pct >= 0 ? "var(--up)" : "var(--down)",
                        }}>
                          {row.yoy_change_pct != null ? fmtPct(row.yoy_change_pct) : "—"}
                        </td>
                        <td className="num">{row.vacancy_pct != null ? `${row.vacancy_pct.toFixed(1)}%` : "—"}</td>
                        <td style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                          {sourceLabel(row.source)}
                        </td>
                        <td><PriorityPill priority={row.source_priority} /></td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
