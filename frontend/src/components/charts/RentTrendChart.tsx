/**
 * Line chart: rent SAR/sqm/yr over periods, one line per property type.
 * Only renders when at least two distinct periods exist.
 */
import ReactECharts from "echarts-for-react";
import type { RentIndexEntry } from "../../types/api";

interface Props {
  data: RentIndexEntry[];
}

const TYPE_COLORS: Record<string, string> = {
  warehouse:       "#c9922a",
  industrial_land: "#60a5fa",
  factory:         "#4ade80",
  logistics:       "#f472b6",
  office:          "#a78bfa",
  retail:          "#fb923c",
};

export function RentTrendChart({ data }: Props) {
  if (data.length === 0) return null;

  // Only rows with rent data
  const withRent = data.filter(r => r.rent_sar_sqm_annual != null);
  if (withRent.length === 0) return null;

  // Collect sorted periods
  const periods = [...new Set(withRent.map(r => r.period))].sort();
  if (periods.length < 2) return null;

  // Group: property_type → period → median rent
  const byType: Record<string, Record<string, number[]>> = {};
  for (const row of withRent) {
    if (!byType[row.property_type]) byType[row.property_type] = {};
    const byPeriod = byType[row.property_type]!;
    if (!byPeriod[row.period]) byPeriod[row.period] = [];
    byPeriod[row.period]!.push(row.rent_sar_sqm_annual!);
  }

  const series = Object.entries(byType).map(([ptype, byPeriod]) => ({
    name: ptype.replace(/_/g, " "),
    type: "line",
    smooth: true,
    symbol: "circle",
    symbolSize: 5,
    lineStyle: { width: 2, color: TYPE_COLORS[ptype] ?? "#888" },
    itemStyle: { color: TYPE_COLORS[ptype] ?? "#888" },
    data: periods.map(p => {
      const vals = byPeriod[p];
      if (!vals || vals.length === 0) return null;
      const sorted = [...vals].sort((a, b) => a - b);
      return sorted[Math.floor(sorted.length / 2)]; // median
    }),
    connectNulls: true,
  }));

  const option = {
    backgroundColor: "transparent",
    grid: { top: 24, right: 24, bottom: 48, left: 72 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { seriesName: string; value: number | null; axisValue: string }[]) => {
        const rows = params
          .filter(p => p.value != null)
          .map(p => `${p.seriesName}: ${p.value!.toLocaleString("en-US", { maximumFractionDigits: 0 })} SAR`)
          .join("<br/>");
        return `<b>${params[0]?.axisValue}</b><br/>${rows}`;
      },
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 11 },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#6B7280", fontSize: 9 },
      itemWidth: 14,
      itemHeight: 3,
    },
    xAxis: {
      type: "category",
      data: periods,
      axisLabel: { color: "#A3A3A3", fontSize: 9 },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 9,
        formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v),
      },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: "#F0F0F0" } },
    },
    series,
  };

  return (
    <div style={{ marginTop: "20px" }}>
      <div style={{
        fontSize: "9px",
        fontWeight: 700,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: "var(--text-tertiary)",
        marginBottom: "8px",
      }}>
        Rent Trend (SAR/sqm/yr, median by period)
      </div>
      <ReactECharts
        option={option}
        style={{ height: "220px", width: "100%" }}
      />
    </div>
  );
}
