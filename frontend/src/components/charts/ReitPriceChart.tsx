/**
 * Line chart — REIT price history for the three tracked industrial REITs.
 * Fetches last 90 days of snapshots per ticker.
 */
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { ReitSnapshot } from "../../types/api";

const TICKERS = ["4331.SR", "4339.SR", "4340.SR"];
const TICKER_NAMES: Record<string, string> = {
  "4331.SR": "AlJazira Mawten",
  "4339.SR": "Derayah",
  "4340.SR": "Al Rajhi",
};
const COLORS = ["#c9922a", "#60a5fa", "#a78bfa"];

function usePriceHistory() {
  return useQuery<ReitSnapshot[]>({
    queryKey: ["reit-history"],
    queryFn: () =>
      api.get<ReitSnapshot[]>(`/api/reit-snapshots?limit=500`),
    refetchInterval: 5 * 60_000,
  });
}

export function ReitPriceChart() {
  const { data: snapshots, isLoading } = usePriceHistory();

  if (isLoading) return null;
  if (!snapshots || snapshots.length === 0) return null;

  // Group by ticker → sorted by date
  const byTicker: Record<string, ReitSnapshot[]> = {};
  for (const s of snapshots) {
    if (!TICKERS.includes(s.ticker)) continue;
    (byTicker[s.ticker] ??= []).push(s);
  }
  for (const arr of Object.values(byTicker)) {
    arr.sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date));
  }

  const allDates = [
    ...new Set(snapshots.map((s) => s.snapshot_date)),
  ].sort();

  const series = TICKERS.filter((t) => byTicker[t]?.length).map((ticker, i) => {
    const map = Object.fromEntries(
      (byTicker[ticker] ?? []).map((s) => [s.snapshot_date, s.price_sar])
    );
    return {
      name: TICKER_NAMES[ticker] ?? ticker,
      type: "line",
      data: allDates.map((d) => map[d] ?? null),
      connectNulls: true,
      showSymbol: false,
      lineStyle: { width: 2, color: COLORS[i] },
      itemStyle: { color: COLORS[i] },
    };
  });

  if (series.length === 0) return null;

  const option = {
    backgroundColor: "transparent",
    grid: { top: 32, right: 24, bottom: 40, left: 56 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string }>) => {
        const date = params[0]?.axisValue ?? "";
        const lines = params
          .filter((p) => p.value != null)
          .map((p) => `${p.seriesName}: SAR ${(p.value as number).toFixed(2)}`);
        return [date, ...lines].join("<br/>");
      },
    },
    legend: {
      data: series.map((s) => s.name),
      textStyle: { color: "#6B7280", fontSize: 10 },
      top: 4,
    },
    xAxis: {
      type: "category",
      data: allDates,
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 9,
        formatter: (v: string) => v.slice(5), // MM-DD
      },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 9,
        formatter: (v: number) => `${v.toFixed(0)}`,
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
        Industrial REIT Price History (SAR)
      </div>
      <ReactECharts
        option={option}
        style={{ height: "220px", width: "100%" }}
      />
    </div>
  );
}
