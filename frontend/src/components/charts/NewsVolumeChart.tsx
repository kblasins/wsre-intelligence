/**
 * Stacked area chart — weekly article count by source over the last N weeks.
 * Shows news coverage trends: which sources are active, volume spikes.
 */
import ReactECharts from "echarts-for-react";
import type { NewsVolumeRow } from "../../hooks/useMarketData";

const SOURCE_LABELS: Record<string, string> = {
  argaam_en: "Argaam EN",
  argaam_ar: "Argaam AR",
  modon: "MODON",
  saudi_gazette: "Saudi Gazette",
  arab_news: "Arab News",
  knight_frank: "Knight Frank",
};

const PALETTE = ["#c9922a", "#60a5fa", "#a78bfa", "#34d399", "#f87171", "#fb923c", "#e879f9", "#fbbf24"];

interface Props {
  data: NewsVolumeRow[];
}

export function NewsVolumeChart({ data }: Props) {
  if (!data || data.length === 0) return null;

  // Extract all unique weeks and sources
  const weeks = [...new Set(data.map(r => r.week))].sort();
  const sources = [...new Set(data.map(r => r.source))];

  // Build a lookup: week -> source -> count
  const lookup: Record<string, Record<string, number>> = {};
  for (const r of data) {
    (lookup[r.week] ??= {})[r.source] = r.count;
  }

  const series = sources.map((source, i) => ({
    name: SOURCE_LABELS[source] ?? source,
    type: "line" as const,
    stack: "total",
    areaStyle: { opacity: 0.7 },
    showSymbol: false,
    lineStyle: { width: 0 },
    itemStyle: { color: PALETTE[i % PALETTE.length] },
    data: weeks.map(w => lookup[w]?.[source] ?? 0),
  }));

  const option = {
    backgroundColor: "transparent",
    grid: { top: 32, right: 24, bottom: 40, left: 36 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10, fontFamily: "monospace" },
      formatter: (params: Array<{ seriesName: string; value: number; color: string; axisValue: string }>) => {
        const date = params[0]?.axisValue ?? "";
        const total = params.reduce((s, p) => s + (p.value ?? 0), 0);
        const lines = params
          .filter(p => p.value > 0)
          .map(p => `<span style="color:${p.color}">■</span> ${p.seriesName}: ${p.value}`);
        return [`<b>${date}</b>: ${total} articles`, ...lines].join("<br/>");
      },
    },
    legend: {
      data: series.map(s => s.name),
      textStyle: { color: "#6B7280", fontSize: 9 },
      top: 4,
      left: 0,
    },
    xAxis: {
      type: "category",
      data: weeks,
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 8,
        formatter: (v: string) => v.slice(5), // MM-DD
      },
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: { color: "#A3A3A3", fontSize: 9 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: "#F0F0F0" } },
    },
    series,
  };

  return (
    <div style={{ marginTop: "20px" }}>
      <div style={{
        fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: "var(--text-tertiary)",
        marginBottom: "4px",
      }}>
        News Coverage: Articles per Week by Source
      </div>
      <ReactECharts
        option={option}
        style={{ height: "160px", width: "100%" }}
      />
    </div>
  );
}
