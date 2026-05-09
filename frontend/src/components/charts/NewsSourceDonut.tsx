/**
 * Donut chart — article count by source, to show pipeline coverage at a glance.
 */
import ReactECharts from "echarts-for-react";
import { useNews } from "../../hooks/useMarketData";

const SOURCE_LABELS: Record<string, string> = {
  argaam_en: "Argaam EN",
  argaam_ar: "Argaam AR",
  modon: "MODON",
  saudi_gazette: "Saudi Gazette",
  arab_news: "Arab News",
  knight_frank: "Knight Frank",
};

const PALETTE = ["#c9922a", "#60a5fa", "#a78bfa", "#34d399", "#f87171", "#fb923c"];

export function NewsSourceDonut() {
  const { data: articles } = useNews(500);

  if (!articles || articles.length === 0) return null;

  const counts: Record<string, number> = {};
  for (const a of articles) {
    counts[a.source] = (counts[a.source] ?? 0) + 1;
  }

  const chartData = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([source, count], i) => ({
      name: SOURCE_LABELS[source] ?? source,
      value: count,
      itemStyle: { color: PALETTE[i % PALETTE.length] },
    }));

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10 },
      formatter: "{b}: {c} ({d}%)",
    },
    legend: { show: false },
    series: [
      {
        type: "pie",
        radius: ["55%", "80%"],
        center: ["50%", "50%"],
        data: chartData,
        label: {
          show: true,
          position: "outside",
          color: "#6B7280",
          fontSize: 9,
          formatter: "{b}\n{c}",
        },
        labelLine: { lineStyle: { color: "#E5E7EB" } },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,0.15)" },
        },
      },
    ],
  };

  return (
    <div style={{ marginTop: "20px" }}>
      <div style={{
        fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: "var(--text-tertiary)",
        marginBottom: "4px",
      }}>
        Articles by Source
      </div>
      <ReactECharts
        option={option}
        style={{ height: "180px", width: "100%" }}
      />
    </div>
  );
}
