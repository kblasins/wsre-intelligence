/**
 * Heatmap of YoY rent change % by district × property type.
 * Uses ECharts heatmap — colour scale: red (−) → white (0) → green (+).
 */
import ReactECharts from "echarts-for-react";
import type { RentIndexEntry } from "../../types/api";

interface Props {
  data: RentIndexEntry[];
}

export function RentHeatmap({ data }: Props) {
  if (data.length === 0) return null;

  // Only rows with YoY data
  const withYoy = data.filter((r) => r.yoy_change_pct != null);
  if (withYoy.length === 0) return null;

  const districts = [...new Set(withYoy.map((r) => r.district ?? "Market-wide"))];
  const ptypes = [...new Set(withYoy.map((r) => r.property_type))];

  // Build value matrix
  const cellData: [number, number, number][] = [];
  for (const row of withYoy) {
    const x = ptypes.indexOf(row.property_type);
    const y = districts.indexOf(row.district ?? "Market-wide");
    cellData.push([x, y, row.yoy_change_pct!]);
  }

  const maxAbs = Math.max(...withYoy.map((r) => Math.abs(r.yoy_change_pct!)), 5);

  const option = {
    backgroundColor: "transparent",
    grid: { top: 32, right: 16, bottom: 48, left: 120 },
    tooltip: {
      formatter: (p: { data: [number, number, number] }) =>
        `${districts[p.data[1]]} · ${ptypes[p.data[0]]}<br/>${p.data[2] >= 0 ? "+" : ""}${p.data[2].toFixed(1)}% YoY`,
    },
    xAxis: {
      type: "category",
      data: ptypes.map((p) => p.replace(/_/g, " ")),
      axisLabel: { color: "#A3A3A3", fontSize: 10 },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitArea: { show: false },
    },
    yAxis: {
      type: "category",
      data: districts,
      axisLabel: { color: "#A3A3A3", fontSize: 10 },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitArea: { show: false },
    },
    visualMap: {
      min: -maxAbs,
      max: maxAbs,
      calculable: false,
      show: false,
      inRange: {
        color: ["#ef4444", "#ffffff", "#22c55e"],
      },
    },
    series: [
      {
        type: "heatmap",
        data: cellData,
        label: {
          show: true,
          formatter: (p: { data: [number, number, number] }) =>
            `${p.data[2] >= 0 ? "+" : ""}${p.data[2].toFixed(1)}%`,
          color: "#374151",
          fontSize: 11,
        },
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,32,96,0.2)" },
        },
      },
    ],
  };

  const height = Math.max(120, districts.length * 40 + 80);

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
        YoY Change % Heatmap
      </div>
      <ReactECharts
        option={option}
        style={{ height: `${height}px`, width: "100%" }}
      />
    </div>
  );
}
