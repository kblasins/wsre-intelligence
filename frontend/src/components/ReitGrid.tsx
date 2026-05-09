import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { useReitSnapshots } from "../hooks/useMarketData";
import { formatSAR, formatDate, formatPct } from "../lib/format";
import type { ReitSnapshot } from "../types/api";
import { ReitPriceChart } from "./charts/ReitPriceChart";
import { ReitNavComparisonChart } from "./charts/ReitNavComparisonChart";
import { api } from "../lib/api";

export function ReitGrid() {
  const { data: reits, isLoading, error } = useReitSnapshots();
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  if (isLoading) return <GridSkeleton />;
  if (error || !reits) return (
    <p style={{ color: "var(--text-tertiary)", fontSize: "13px", marginBottom: "32px" }}>
      Could not load REIT data.
    </p>
  );

  const industrial = reits.filter((r) => r.industrial === "yes");
  const secondary  = reits.filter((r) => r.industrial !== "yes")
    .sort((a, b) => a.ticker.localeCompare(b.ticker));

  const latestDate = reits[0]?.snapshot_date;
  const selectedReit = selectedTicker ? reits.find(r => r.ticker === selectedTicker) : null;

  return (
    <section style={{ marginBottom: "48px" }}>

      {/* Section header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
        <h2 className="ws-section-h">REIT Market Prices</h2>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {latestDate && (
            <span className="ws-small">{formatDate(latestDate)} · 15-min delayed · yfinance</span>
          )}
          {reits.length > 0 && (
            <a
              href="/api/reit-snapshots/export.csv"
              download="reit_snapshots.csv"
              className="btn ghost"
              style={{ fontSize: "11px", textDecoration: "none" }}
            >
              ↓ CSV
            </a>
          )}
        </div>
      </div>

      {/* Industrial REITs */}
      <div style={{ marginBottom: "8px" }}>
        <div className="ws-upper" style={{ marginBottom: "10px" }}>Industrial Exposure</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1px", background: "var(--border)" }}>
          {industrial.map((reit, i) => (
            <FeaturedCard
              key={reit.ticker}
              reit={reit}
              index={i}
              isSelected={selectedTicker === reit.ticker}
              onClick={() => setSelectedTicker(selectedTicker === reit.ticker ? null : reit.ticker)}
            />
          ))}
        </div>
      </div>

      <div style={{ height: "1px", background: "var(--border)", margin: "20px 0" }} />

      {/* All other REITs */}
      <div>
        <div className="ws-upper" style={{ marginBottom: "10px" }}>All Listed REITs</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(148px, 1fr))", gap: "1px", background: "var(--border)" }}>
          {secondary.map((reit, i) => (
            <CompactCard
              key={reit.ticker}
              reit={reit}
              index={i + industrial.length}
              isSelected={selectedTicker === reit.ticker}
              onClick={() => setSelectedTicker(selectedTicker === reit.ticker ? null : reit.ticker)}
            />
          ))}
        </div>
      </div>

      {selectedReit && (
        <ReitDetailPanel reit={selectedReit} onClose={() => setSelectedTicker(null)} />
      )}

      <ReitNavComparisonChart reits={reits} />
      <ReitPriceChart />
    </section>
  );
}

function FeaturedCard({
  reit, index, isSelected, onClick,
}: {
  reit: ReitSnapshot;
  index: number;
  isSelected: boolean;
  onClick: () => void;
}) {
  const tickerCode = reit.ticker.replace(".SR", "");
  const navPct = reit.nav_discount_pct;

  return (
    <div
      className="fade-up"
      style={{
        animationDelay: `${index * 80}ms`,
        background: isSelected ? "var(--bg-selected)" : "var(--bg-surface)",
        padding: "20px",
        cursor: "pointer",
        position: "relative",
        borderLeft: isSelected ? `3px solid var(--brand-navy)` : "3px solid transparent",
        transition: "background 150ms ease, border-color 150ms ease",
      }}
      onClick={onClick}
      onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--bg-hover)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = isSelected ? "var(--bg-selected)" : "var(--bg-surface)"; }}
    >
      {/* Ticker */}
      <div style={{
        fontSize: "11px", fontWeight: 500, textTransform: "uppercase",
        letterSpacing: "0.5px", color: "var(--brand-navy)", marginBottom: "4px",
        fontFamily: "'IBM Plex Mono', monospace",
      }}>
        {tickerCode}
        <span style={{ float: "right", fontSize: "10px", color: "var(--text-tertiary)", fontWeight: 400, letterSpacing: 0 }}>
          Industrial
        </span>
      </div>

      {/* Name */}
      <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "12px", lineHeight: 1.3 }}>
        {reit.name.replace(" REIT", "")}
      </div>

      {/* Price */}
      <div style={{
        fontSize: "28px", fontWeight: 500, color: "var(--text-primary)",
        fontVariantNumeric: "tabular-nums", lineHeight: 1.1, marginBottom: "6px",
        fontFamily: "'IBM Plex Mono', monospace",
      }}>
        {reit.price_sar != null ? formatSAR(reit.price_sar, 2) : "—"}
      </div>

      {/* NAV delta */}
      <div style={{
        fontSize: "13px",
        color: navPct != null
          ? (navPct < 0 ? "var(--down)" : "var(--up)")
          : "var(--text-tertiary)",
        fontVariantNumeric: "tabular-nums",
      }}>
        {navPct != null ? `${formatPct(navPct, true)} to NAV` : "NAV pending"}
      </div>
    </div>
  );
}

function CompactCard({
  reit, index, isSelected, onClick,
}: {
  reit: ReitSnapshot;
  index: number;
  isSelected: boolean;
  onClick: () => void;
}) {
  const tickerCode = reit.ticker.replace(".SR", "");

  return (
    <div
      className="fade-up"
      style={{
        animationDelay: `${index * 30}ms`,
        background: isSelected ? "var(--bg-selected)" : "var(--bg-surface)",
        padding: "12px 14px",
        cursor: "pointer",
        borderLeft: isSelected ? `2px solid var(--brand-navy)` : "2px solid transparent",
        transition: "background 140ms ease",
      }}
      onClick={onClick}
      onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--bg-hover)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = isSelected ? "var(--bg-selected)" : "var(--bg-surface)"; }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", fontWeight: 500,
          color: isSelected ? "var(--brand-navy)" : "var(--text-primary)",
        }}>
          {tickerCode}
        </span>
        {reit.industrial === "verify" && (
          <span style={{ fontSize: "9px", color: "var(--text-tertiary)", letterSpacing: "0.1em" }}>VFY</span>
        )}
      </div>

      <div style={{
        fontSize: "11px", color: "var(--text-tertiary)", marginBottom: "8px",
        lineHeight: 1.3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {shortName(reit.name)}
      </div>

      <div style={{
        fontFamily: "'IBM Plex Mono', monospace", fontSize: "14px", fontWeight: 500,
        color: "var(--text-primary)", fontVariantNumeric: "tabular-nums",
      }}>
        {reit.price_sar != null ? formatSAR(reit.price_sar, 2) : "—"}
      </div>
    </div>
  );
}

function shortName(name: string): string {
  return name.replace(" REIT", "").replace(" Saudi", "").trim();
}

function useTickerHistory(ticker: string) {
  return useQuery<ReitSnapshot[]>({
    queryKey: ["reit-ticker", ticker],
    queryFn: () => api.get<ReitSnapshot[]>(`/api/reit-snapshots?ticker=${ticker}&limit=200`),
    staleTime: 5 * 60_000,
  });
}

function ReitDetailPanel({ reit, onClose }: { reit: ReitSnapshot; onClose: () => void }) {
  const { data: history } = useTickerHistory(reit.ticker);
  const sorted = (history ?? []).sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date));
  const dates = sorted.map(s => s.snapshot_date);
  const prices = sorted.map(s => s.price_sar);
  const navDiscounts = sorted.map(s => s.nav_discount_pct);
  const hasNav = navDiscounts.some(v => v != null);
  const tickerCode = reit.ticker.replace(".SR", "");

  const option = dates.length > 1 ? {
    backgroundColor: "transparent",
    grid: { top: 24, right: hasNav ? 56 : 16, bottom: 32, left: 52 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E5E5",
      textStyle: { color: "#1A1A1A", fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string }>) => {
        const date = params[0]?.axisValue ?? "";
        const lines = params
          .filter(p => p.value != null)
          .map(p => {
            if (p.seriesName === "Price") return `Price: SAR ${(p.value as number).toFixed(2)}`;
            return `NAV Δ: ${(p.value as number).toFixed(1)}%`;
          });
        return [date, ...lines].join("<br/>");
      },
    },
    legend: hasNav ? {
      data: ["Price", "NAV Discount %"],
      textStyle: { color: "#525252", fontSize: 10 },
      top: 2, right: 16,
    } : undefined,
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: "#A3A3A3", fontSize: 10, formatter: (v: string) => v.slice(5) },
      axisLine: { lineStyle: { color: "#E5E5E5" } },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value",
        name: "SAR",
        nameTextStyle: { color: "#A3A3A3", fontSize: 9 },
        axisLabel: { color: "#A3A3A3", fontSize: 10, formatter: (v: number) => v.toFixed(0) },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#F0F0F0" } },
      },
      ...(hasNav ? [{
        type: "value",
        name: "%",
        nameTextStyle: { color: "#A3A3A3", fontSize: 9 },
        position: "right",
        axisLabel: { color: "#A3A3A3", fontSize: 10, formatter: (v: number) => `${v.toFixed(0)}%` },
        axisLine: { show: false },
        splitLine: { show: false },
      }] : []),
    ],
    series: [
      {
        name: "Price",
        type: "line",
        yAxisIndex: 0,
        data: prices,
        showSymbol: false,
        lineStyle: { width: 2, color: "#002060" },
        areaStyle: { color: "rgba(0,32,96,0.04)" },
      },
      ...(hasNav ? [{
        name: "NAV Discount %",
        type: "line",
        yAxisIndex: 1,
        data: navDiscounts,
        showSymbol: false,
        lineStyle: { width: 1.5, color: "#8B6914", type: "dashed" as const },
        itemStyle: { color: "#8B6914" },
      }] : []),
    ],
  } : null;

  return (
    <div style={{
      marginTop: "1px",
      background: "var(--bg-surface)",
      borderLeft: "3px solid var(--brand-navy)",
      padding: "20px 24px",
      animation: "fadeUp 0.2s ease both",
      position: "relative",
      border: "1px solid var(--border)",
    }}>
      <button
        onClick={onClose}
        style={{
          position: "absolute", top: "12px", right: "16px",
          background: "transparent", border: "none",
          color: "var(--text-tertiary)", fontSize: "18px", cursor: "pointer",
        }}
      >×</button>

      <div style={{ display: "flex", alignItems: "baseline", gap: "12px", marginBottom: "16px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: "18px", fontWeight: 500,
          color: "var(--brand-navy)",
        }}>
          {tickerCode}
        </span>
        <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
          {reit.name}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "1px", background: "var(--border)", marginBottom: "20px" }}>
        {[
          { label: "Price",        value: reit.price_sar != null ? `SAR ${reit.price_sar.toFixed(2)}` : "—" },
          { label: "NAV/Unit",     value: reit.nav_per_unit_sar != null ? `SAR ${reit.nav_per_unit_sar.toFixed(2)}` : "—" },
          { label: "NAV Discount", value: reit.nav_discount_pct != null ? `${reit.nav_discount_pct > 0 ? "+" : ""}${reit.nav_discount_pct.toFixed(1)}%` : "—" },
          { label: "Distribution", value: reit.distribution_per_unit_sar != null ? `SAR ${reit.distribution_per_unit_sar.toFixed(2)}` : "—" },
          { label: "Occupancy",    value: reit.occupancy_pct != null ? `${reit.occupancy_pct.toFixed(1)}%` : "—" },
          { label: "As of",        value: reit.snapshot_date },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: "var(--bg-surface)", padding: "12px 14px" }}>
            <div className="label" style={{ fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.4px", color: "var(--text-secondary)", fontWeight: 500 }}>
              {label}
            </div>
            <div style={{
              fontFamily: "'IBM Plex Mono', monospace", fontSize: "13px",
              color: "var(--text-primary)", fontVariantNumeric: "tabular-nums", marginTop: "4px",
            }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {option ? (
        <ReactECharts option={option} style={{ height: "160px", width: "100%" }} />
      ) : (
        <div style={{ fontSize: "12px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace" }}>
          No price history available.
        </div>
      )}
    </div>
  );
}

function GridSkeleton() {
  return (
    <section style={{ marginBottom: "48px" }}>
      <div className="load-bar" style={{ marginBottom: "8px" }}><div className="load-bar-inner" /></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1px", background: "var(--border)" }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ height: "120px", background: "var(--bg-surface)", opacity: 0.5 }} />
        ))}
      </div>
    </section>
  );
}
