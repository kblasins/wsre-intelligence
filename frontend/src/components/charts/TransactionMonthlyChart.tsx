/**
 * Monthly bar + line chart using the /api/transactions/aggregate endpoint.
 * Shows deal count (bars) and total value in SAR (line) per month.
 */
import ReactECharts from "echarts-for-react";
import type { TransactionAggregate } from "../../hooks/useMarketData";

interface Props {
  data: TransactionAggregate[];
}

function fmtSAR(v: number) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  return `${(v / 1_000).toFixed(0)}K`;
}

export function TransactionMonthlyChart({ data }: Props) {
  if (data.length < 2) return null;

  const months = data.map(r => r.month);
  const counts = data.map(r => r.count);
  const values = data.map(r => r.total_sar);

  const option = {
    backgroundColor: "transparent",
    grid: { top: 28, right: 64, bottom: 44, left: 56 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: (params: { seriesName: string; value: number; axisValue: string }[]) => {
        const rows = params
          .map(p =>
            p.seriesName === "Deals"
              ? `Deals: ${p.value}`
              : `Value: SAR ${fmtSAR(p.value)}`
          )
          .join("<br/>");
        return `<b>${params[0]?.axisValue}</b><br/>${rows}`;
      },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#6B7280", fontSize: 9 },
      itemWidth: 12,
      itemHeight: 3,
    },
    xAxis: {
      type: "category",
      data: months,
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 8,
        rotate: 30,
      },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value",
        name: "Deals",
        nameTextStyle: { color: "#A3A3A3", fontSize: 8 },
        axisLabel: { color: "#A3A3A3", fontSize: 8 },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#F0F0F0" } },
        minInterval: 1,
      },
      {
        type: "value",
        name: "SAR",
        nameTextStyle: { color: "#A3A3A3", fontSize: 8 },
        axisLabel: {
          color: "#A3A3A3",
          fontSize: 8,
          formatter: (v: number) => fmtSAR(v),
        },
        axisLine: { show: false },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "Deals",
        type: "bar",
        yAxisIndex: 0,
        data: counts,
        barMaxWidth: 18,
        itemStyle: {
          color: "rgba(201,146,42,0.3)",
          borderColor: "rgba(201,146,42,0.6)",
          borderWidth: 1,
          borderRadius: [2, 2, 0, 0],
        },
      },
      {
        name: "Total SAR",
        type: "line",
        yAxisIndex: 1,
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { width: 2, color: "#c9922a" },
        itemStyle: { color: "#c9922a" },
        areaStyle: { color: "rgba(201,146,42,0.06)" },
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
        Monthly Transaction Volume
      </div>
      <ReactECharts
        option={option}
        style={{ height: "200px", width: "100%" }}
      />
    </div>
  );
}
