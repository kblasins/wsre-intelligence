/**
 * Mini bar chart — daily LLM spend over the last N days.
 * Used in the Admin page budget section.
 */
import ReactECharts from "echarts-for-react";

interface DaySpend {
  day: string;
  spend_usd: number;
  calls: number;
}

interface Props {
  data: DaySpend[];
  dailyCap: number;
}

export function BudgetSparkline({ data, dailyCap }: Props) {
  if (data.length === 0) return null;

  const days = data.map(r => r.day.slice(5)); // MM-DD
  const spends = data.map(r => r.spend_usd);
  const calls = data.map(r => r.calls);

  const option = {
    backgroundColor: "transparent",
    grid: { top: 20, right: 48, bottom: 36, left: 52 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: (params: { seriesName: string; value: number; axisValue: string }[]) => {
        const spend = params.find(p => p.seriesName === "Spend");
        const callCount = params.find(p => p.seriesName === "Calls");
        return (
          `<b>${params[0]?.axisValue}</b><br/>` +
          `Spend: $${spend?.value.toFixed(4) ?? "—"}<br/>` +
          `Calls: ${callCount?.value ?? "—"}`
        );
      },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#6B7280", fontSize: 9 },
      itemWidth: 10,
      itemHeight: 3,
    },
    xAxis: {
      type: "category",
      data: days,
      axisLabel: { color: "#A3A3A3", fontSize: 8, rotate: 30 },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value",
        name: "$",
        nameTextStyle: { color: "#A3A3A3", fontSize: 8 },
        axisLabel: {
          color: "#A3A3A3",
          fontSize: 8,
          formatter: (v: number) => `$${v.toFixed(2)}`,
        },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#F0F0F0" } },
        max: dailyCap,
      },
      {
        type: "value",
        name: "Calls",
        nameTextStyle: { color: "#A3A3A3", fontSize: 8 },
        axisLabel: { color: "#A3A3A3", fontSize: 8 },
        axisLine: { show: false },
        splitLine: { show: false },
        minInterval: 1,
      },
    ],
    series: [
      {
        name: "Spend",
        type: "bar",
        yAxisIndex: 0,
        data: spends,
        barMaxWidth: 18,
        itemStyle: {
          color: (params: { value: number }) =>
            params.value / dailyCap > 0.8
              ? "#ef4444"
              : params.value / dailyCap > 0.5
                ? "#f97316"
                : "#002060",
          borderRadius: [2, 2, 0, 0],
        },
        markLine: {
          silent: true,
          lineStyle: { color: "#D1D5DB", type: "dashed" },
          data: [{ yAxis: dailyCap, name: "Cap" }],
          label: {
            color: "#9CA3AF",
            fontSize: 8,
            formatter: `Cap $${dailyCap}`,
          },
        },
      },
      {
        name: "Calls",
        type: "line",
        yAxisIndex: 1,
        data: calls,
        smooth: true,
        symbol: "circle",
        symbolSize: 3,
        lineStyle: { width: 1, color: "#9CA3AF" },
        itemStyle: { color: "#9CA3AF" },
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: "160px", width: "100%" }}
    />
  );
}
