/**
 * Line chart — weekly transaction count and total value (SAR) over time.
 * Dual-axis: count on left, value on right.
 */
import ReactECharts from "echarts-for-react";
import type { Transaction } from "../../types/api";

interface Props {
  transactions: Transaction[];
}

function weekKey(dateStr: string): string {
  const d = new Date(dateStr);
  // Monday of the week
  const day = d.getDay();
  const diff = (day === 0 ? -6 : 1 - day);
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(iso: string): string {
  const [y, m, dy] = iso.split("-").map(Number);
  return `${dy} ${MONTHS[(m ?? 1) - 1]} ${y}`;
}

function fmtM(v: number) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  return `${(v / 1_000).toFixed(0)}K`;
}

export function TransactionTrendChart({ transactions }: Props) {
  if (transactions.length === 0) return null;

  // Bucket by week
  const byWeek: Record<string, { count: number; value: number }> = {};
  for (const t of transactions) {
    if (!t.transaction_date) continue;
    const wk = weekKey(t.transaction_date);
    if (!byWeek[wk]) byWeek[wk] = { count: 0, value: 0 };
    byWeek[wk].count += 1;
    byWeek[wk].value += t.price_sar ?? 0;
  }

  const weeks = Object.keys(byWeek).sort();
  if (weeks.length < 2) return null;

  const counts = weeks.map(w => byWeek[w]!.count);
  const values = weeks.map(w => byWeek[w]!.value);

  const option = {
    backgroundColor: "transparent",
    grid: { top: 28, right: 60, bottom: 48, left: 48 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: (params: { seriesName: string; value: number; axisValue: string }[]) => {
        const rows = params.map(p =>
          `${p.seriesName}: ${p.seriesName === "Count" ? p.value : "SAR " + fmtM(p.value)}`
        ).join("<br/>");
        return `<b>${fmtDate(params[0]?.axisValue ?? "")}</b><br/>${rows}`;
      },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#6B7280", fontSize: 9 },
      itemWidth: 14,
      itemHeight: 3,
    },
    xAxis: {
      type: "category",
      data: weeks,
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 8,
        rotate: 30,
        formatter: (v: string) => { const [, m, d] = v.split("-").map(Number); return `${d} ${MONTHS[(m ?? 1) - 1]}`; },
      },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value",
        name: "Count",
        nameTextStyle: { color: "#A3A3A3", fontSize: 8 },
        axisLabel: { color: "#A3A3A3", fontSize: 8 },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#F0F0F0" } },
      },
      {
        type: "value",
        name: "Value",
        nameTextStyle: { color: "#A3A3A3", fontSize: 8 },
        axisLabel: {
          color: "#A3A3A3",
          fontSize: 8,
          formatter: (v: number) => fmtM(v),
        },
        axisLine: { show: false },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "Count",
        type: "bar",
        yAxisIndex: 0,
        data: counts,
        barMaxWidth: 16,
        itemStyle: { color: "rgba(201,146,42,0.35)", borderRadius: [2, 2, 0, 0] },
      },
      {
        name: "Value (SAR)",
        type: "line",
        yAxisIndex: 1,
        data: values,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color: "#c9922a" },
        areaStyle: { color: "rgba(201,146,42,0.07)" },
      },
    ],
  };

  return (
    <div style={{ marginTop: "16px" }}>
      <div style={{
        fontSize: "9px",
        fontWeight: 700,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: "var(--text-tertiary)",
        marginBottom: "6px",
      }}>
        Weekly Transaction Volume
      </div>
      <ReactECharts
        option={option}
        style={{ height: "200px", width: "100%" }}
      />
    </div>
  );
}
