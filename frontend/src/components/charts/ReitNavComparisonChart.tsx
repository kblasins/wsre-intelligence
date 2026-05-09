/**
 * Horizontal bar chart comparing NAV discount/premium % across all tracked REITs.
 * Positive = trading at premium to NAV; negative = discount.
 */
import ReactECharts from "echarts-for-react";
import type { ReitSnapshot } from "../../types/api";

interface Props {
  reits: ReitSnapshot[];
}

export function ReitNavComparisonChart({ reits }: Props) {
  const withNav = reits.filter(r => r.nav_discount_pct != null);
  if (withNav.length < 2) return null;

  // Sort by nav_discount_pct ascending (biggest discount first)
  const sorted = [...withNav].sort(
    (a, b) => (a.nav_discount_pct ?? 0) - (b.nav_discount_pct ?? 0)
  );

  const names = sorted.map(r => r.name ?? r.ticker);
  const values = sorted.map(r => r.nav_discount_pct ?? 0);
  const colors = values.map(v =>
    v > 5 ? "#f87171" : v > 0 ? "#fb923c" : v > -10 ? "#4ade80" : "#22c55e"
  );

  const option = {
    backgroundColor: "transparent",
    grid: { top: 8, right: 48, bottom: 8, left: 120, containLabel: false },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: (params: { name: string; value: number }[]) => {
        const p = params[0];
        const sign = (p?.value ?? 0) >= 0 ? "+" : "";
        return `${p?.name ?? ""}: <b>${sign}${(p?.value ?? 0).toFixed(2)}%</b> to NAV`;
      },
    },
    xAxis: {
      type: "value",
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 8,
        formatter: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`,
      },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { lineStyle: { color: "#F0F0F0" } },
    },
    yAxis: {
      type: "category",
      data: names,
      axisLabel: { color: "#6B7280", fontSize: 9 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
        barMaxWidth: 14,
        label: {
          show: true,
          position: values.map(v => (v >= 0 ? "right" : "left")),
          color: "#9CA3AF",
          fontSize: 8,
          formatter: (p: { value: number }) =>
            `${p.value >= 0 ? "+" : ""}${p.value.toFixed(1)}%`,
        },
        markLine: {
          silent: true,
          lineStyle: { color: "#D1D5DB", type: "solid" },
          data: [{ xAxis: 0 }],
          label: { show: false },
          symbol: "none",
        },
      },
    ],
  };

  return (
    <div style={{ marginTop: "24px" }}>
      <div style={{
        fontSize: "9px",
        fontWeight: 700,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: "var(--text-tertiary)",
        marginBottom: "8px",
      }}>
        NAV Premium / Discount (%)
        <span style={{ marginLeft: "8px", fontWeight: 400, color: "var(--text-tertiary)" }}>
          (negative = trading below NAV)
        </span>
      </div>
      <ReactECharts
        option={option}
        style={{ height: `${Math.max(120, withNav.length * 28)}px`, width: "100%" }}
      />
    </div>
  );
}
