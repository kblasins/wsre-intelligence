import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Listing } from "../types/api";
import { formatDate } from "../lib/format";
import { useListingsAggregate } from "../hooks/useMarketData";
import { ListingsPriceChart } from "./charts/ListingsPriceChart";

function useListings() {
  return useQuery<Listing[]>({
    queryKey: ["listings"],
    queryFn: () => api.get<Listing[]>("/api/listings?listing_type=lease&limit=100"),
    refetchInterval: 10 * 60_000,
  });
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function ListingsPanel() {
  const { data: listings, isLoading } = useListings();
  const { data: aggregate } = useListingsAggregate({ listing_type: "lease" });
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null);

  const byDistrict: Record<string, Listing[]> = {};
  for (const l of listings ?? []) {
    const key = l.district ?? "Unknown";
    if (!byDistrict[key]) byDistrict[key] = [];
    byDistrict[key]!.push(l);
  }
  const districts = Object.entries(byDistrict).sort((a, b) => b[1].length - a[1].length);
  const drillRows = selectedDistrict ? (byDistrict[selectedDistrict] ?? []) : [];

  return (
    <div style={{ marginTop: "32px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <h3 className="ws-sub-h">Warehouse Market</h3>
          {selectedDistrict && (
            <span style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "var(--brand-navy)" }}>
              · {selectedDistrict}
              <button
                onClick={() => setSelectedDistrict(null)}
                style={{ background: "transparent", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: "14px", padding: "0 2px", lineHeight: 1 }}
              >×</button>
            </span>
          )}
        </div>
        {listings && listings.length > 0 && (
          <span className="ws-small" style={{ fontVariantNumeric: "tabular-nums" }}>
            {listings.length} listings
          </span>
        )}
      </div>

      {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

      {!isLoading && listings?.length === 0 && (
        <div className="empty-state">
          <p style={{ marginBottom: "6px", fontWeight: 500 }}>No warehouse listings yet.</p>
          <code style={{ fontSize: "12px", color: "var(--brand-navy)", fontFamily: "'IBM Plex Mono', monospace" }}>
            make scrape-aqar
          </code>
          <p className="ws-small" style={{ maxWidth: "380px", marginTop: "6px", lineHeight: 1.6 }}>
            Requires Cloudflare cookie session.
          </p>
        </div>
      )}

      {listings && listings.length > 0 && (
        <div className="ws-card" style={{ padding: 0, overflow: "hidden", animation: "fadeUp 0.4s ease both" }}>
          <table className="ws-table">
            <thead>
              <tr>
                <th>District</th>
                <th className="num">Listings</th>
                <th className="num">Avg Rent SAR/yr</th>
                <th className="num">SAR/sqm/yr</th>
                <th className="num">Avg Area sqm</th>
                <th>Portal</th>
              </tr>
            </thead>
            <tbody>
              {districts.map(([district, rows]) => {
                const rents = rows.map(r => r.rent_sar_annual).filter((v): v is number => v != null);
                const areas = rows.map(r => r.area_sqm).filter((v): v is number => v != null);
                const avgRent = rents.length ? rents.reduce((a, b) => a + b, 0) / rents.length : null;
                const avgArea = areas.length ? areas.reduce((a, b) => a + b, 0) / areas.length : null;
                const perSqm = avgRent != null && avgArea != null && avgArea > 0 ? avgRent / avgArea : null;
                const portals = [...new Set(rows.map(r => r.portal))].join(", ");
                const isSelected = selectedDistrict === district;
                return (
                  <tr
                    key={district}
                    className={isSelected ? "selected" : ""}
                    onClick={() => setSelectedDistrict(isSelected ? null : district)}
                    style={{ cursor: "pointer" }}
                  >
                    <td style={{ fontWeight: isSelected ? 500 : 400 }}>
                      {district}
                      {isSelected && <span style={{ marginLeft: "6px", fontSize: "10px", color: "var(--text-tertiary)" }}>▾</span>}
                    </td>
                    <td className="num">{rows.length}</td>
                    <td className="num">{avgRent != null ? fmt(avgRent) : "—"}</td>
                    <td className="num" style={{ color: "var(--brand-navy)", fontWeight: 500 }}>
                      {perSqm != null ? fmt(perSqm) : "—"}
                    </td>
                    <td className="num">{avgArea != null ? fmt(avgArea) : "—"}</td>
                    <td className="mono">{portals}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {aggregate && aggregate.length > 0 && (
        <div style={{ marginTop: "16px" }}>
          <ListingsPriceChart data={aggregate} />
        </div>
      )}

      {/* Drill-down */}
      {selectedDistrict && drillRows.length > 0 && (
        <div style={{ marginTop: "8px", animation: "fadeUp 0.2s ease both" }}>
          <div className="ws-card" style={{ padding: 0, overflow: "hidden", borderLeft: "3px solid var(--brand-navy)" }}>
            <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontWeight: 500, fontSize: "13px", color: "var(--brand-navy)" }}>{selectedDistrict}</span>
              <span className="ws-small">{drillRows.length} listing{drillRows.length !== 1 ? "s" : ""}</span>
            </div>
            <table className="ws-table">
              <thead>
                <tr>
                  <th className="num">Area sqm</th>
                  <th className="num">Rent SAR/yr</th>
                  <th className="num">SAR/sqm/yr</th>
                  <th>Type</th>
                  <th>Portal</th>
                  <th>Listed</th>
                  <th>Link</th>
                </tr>
              </thead>
              <tbody>
                {drillRows
                  .sort((a, b) => (b.rent_sar_annual ?? 0) - (a.rent_sar_annual ?? 0))
                  .map((row) => {
                    const perSqm = row.rent_sar_annual != null && row.area_sqm != null && row.area_sqm > 0
                      ? row.rent_sar_annual / row.area_sqm : null;
                    return (
                      <tr key={row.id}>
                        <td className="num">{row.area_sqm != null ? fmt(row.area_sqm) : "—"}</td>
                        <td className="num">{row.rent_sar_annual != null ? fmt(row.rent_sar_annual) : "—"}</td>
                        <td className="num" style={{ color: "var(--brand-navy)", fontWeight: 500 }}>
                          {perSqm != null ? fmt(perSqm) : "—"}
                        </td>
                        <td className="mono">{row.property_type.replace(/_/g, " ")}</td>
                        <td className="mono">{row.portal}</td>
                        <td style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                          {row.listed_at ? formatDate(row.listed_at) : "—"}
                        </td>
                        <td>
                          {row.url ? (
                            <a href={row.url} target="_blank" rel="noopener noreferrer"
                              className="btn ghost" style={{ fontSize: "11px", padding: "2px 6px" }}>
                              ↗
                            </a>
                          ) : "—"}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
