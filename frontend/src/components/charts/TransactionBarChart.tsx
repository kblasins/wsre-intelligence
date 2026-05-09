/**
 * Horizontal bar chart — total transaction value by district (last 90 days).
 */
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

interface SummaryRow {
  property_type: string;
  district: string;
  count: number;
  total_sar: number | null;
  avg_price_per_sqm: number | null;
}

function useTransactionSummary() {
  return useQuery<SummaryRow[]>({
    queryKey: ["tx-summary"],
    queryFn: () => api.get<SummaryRow[]>("/api/transactions/summary"),
    refetchInterval: 15 * 60_000,
  });
}

function fmtMillions(v: number) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  return `${(v / 1_000).toFixed(0)}K`;
}

export function TransactionBarChart() {
  const { data: rows } = useTransactionSummary();

  if (!rows || rows.length === 0) return null;

  // Aggregate by district (sum across property types)
  const byDistrict: Record<string, number> = {};
  for (const r of rows) {
    if (r.total_sar) {
      byDistrict[r.district] = (byDistrict[r.district] ?? 0) + r.total_sar;
    }
  }

  const sorted = Object.entries(byDistrict)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  if (sorted.length === 0) return null;

  const option = {
    backgroundColor: "transparent",
    grid: { top: 8, right: 60, bottom: 8, left: 120, containLabel: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "none" },
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: (params: Array<{ name: string; value: number }>) => {
        const p = params[0];
        return p ? `${p.name}<br/>SAR ${fmtMillions(p.value)}` : "";
      },
    },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: sorted.map(([d]) => d),
      inverse: true,
      axisLabel: { color: "#A3A3A3", fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: sorted.map(([, v]) => v),
        barMaxWidth: 20,
        label: {
          show: true,
          position: "right",
          formatter: (p: { value: number }) => `SAR ${fmtMillions(p.value)}`,
          color: "#9CA3AF",
          fontSize: 9,
        },
        itemStyle: {
          color: "var(--brand-navy)",
          borderRadius: [0, 2, 2, 0],
        },
      },
    ],
  };

  const height = sorted.length * 28 + 16;

  return (
    <div style={{ marginTop: "16px" }}>
      <div style={{
        fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: "var(--text-tertiary)",
        marginBottom: "6px",
      }}>
        Total Value by District (SAR, 90 days)
      </div>
      <ReactECharts
        option={option}
        style={{ height: `${height}px`, width: "100%" }}
      />
    </div>
  );
}
