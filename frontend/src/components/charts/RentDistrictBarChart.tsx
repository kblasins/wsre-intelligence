/**
 * Horizontal bar chart — median SAR/sqm/yr by district from rent-index summary.
 * Uses the best available observation per district (lowest source_priority).
 */
import ReactECharts from "echarts-for-react";
import type { RentIndexEntry } from "../../types/api";

interface Props {
  data: RentIndexEntry[];
  propertyType?: string | undefined;
}

export function RentDistrictBarChart({ data, propertyType }: Props) {
  const filtered = data.filter(
    r => r.rent_sar_sqm_annual != null && (!propertyType || r.property_type === propertyType)
  );

  if (filtered.length === 0) return null;

  // Best observation per district: lowest source_priority, then highest rent period
  const best: Record<string, RentIndexEntry> = {};
  for (const row of filtered) {
    const key = row.district ?? "(unknown)";
    const existing = best[key];
    if (
      !existing ||
      row.source_priority < existing.source_priority ||
      (row.source_priority === existing.source_priority && row.period > existing.period)
    ) {
      best[key] = row;
    }
  }

  const sorted = Object.entries(best)
    .map(([district, row]) => ({ district, value: row.rent_sar_sqm_annual! }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 15);

  if (sorted.length < 2) return null;

  const option = {
    backgroundColor: "transparent",
    grid: { top: 8, right: 80, bottom: 8, left: 130, containLabel: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "none" },
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: (params: Array<{ name: string; value: number }>) => {
        const p = params[0];
        return p ? `${p.name}<br/>SAR ${p.value.toLocaleString("en-US", { maximumFractionDigits: 0 })}/sqm/yr` : "";
      },
    },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: sorted.map(d => d.district),
      inverse: true,
      axisLabel: { color: "#A3A3A3", fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: sorted.map(d => d.value),
        barMaxWidth: 20,
        label: {
          show: true,
          position: "right",
          formatter: (p: { value: number }) =>
            `${p.value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,
          color: "#9CA3AF",
          fontSize: 9,
        },
        itemStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: "rgba(201,146,42,0.6)" },
              { offset: 1, color: "rgba(201,146,42,1)" },
            ],
          },
          borderRadius: [0, 2, 2, 0],
        },
      },
    ],
  };

  const height = sorted.length * 28 + 16;
  const label = propertyType
    ? `Rent by District: ${propertyType.replace(/_/g, " ")} (SAR/sqm/yr)`
    : "Rent by District (SAR/sqm/yr)";

  return (
    <div style={{ marginTop: "16px" }}>
      <div style={{
        fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: "var(--text-tertiary)",
        marginBottom: "6px",
      }}>
        {label}
      </div>
      <ReactECharts
        option={option}
        style={{ height: `${height}px`, width: "100%" }}
      />
    </div>
  );
}
