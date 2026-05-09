/**
 * Horizontal bar chart — average asking rent SAR/sqm/yr by district.
 * Compares lease price levels across districts for active warehouse listings.
 */
import ReactECharts from "echarts-for-react";
import type { ListingsAggregate } from "../../hooks/useMarketData";

interface Props {
  data: ListingsAggregate[];
  /** If set, only show rows for this property_type */
  propertyType?: string;
}

export function ListingsPriceChart({ data, propertyType }: Props) {
  const filtered = propertyType
    ? data.filter(r => r.property_type === propertyType)
    : data;

  // Aggregate by district (avg across property types)
  const byDistrict: Record<string, { total: number; count: number; listings: number }> = {};
  for (const r of filtered) {
    if (r.avg_rent_per_sqm == null) continue;
    if (!byDistrict[r.district]) byDistrict[r.district] = { total: 0, count: 0, listings: 0 };
    byDistrict[r.district]!.total += r.avg_rent_per_sqm * r.count;
    byDistrict[r.district]!.count += r.count;
    byDistrict[r.district]!.listings += r.count;
  }

  const rows = Object.entries(byDistrict)
    .map(([district, { total, count, listings }]) => ({
      district,
      avgPerSqm: Math.round(total / count),
      listings,
    }))
    .filter(r => r.avgPerSqm > 0)
    .sort((a, b) => b.avgPerSqm - a.avgPerSqm)
    .slice(0, 15);

  if (rows.length === 0) return null;

  const chartHeight = Math.max(160, rows.length * 30 + 40);

  const option = {
    backgroundColor: "transparent",
    grid: { top: 12, right: 60, bottom: 24, left: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "none" },
      backgroundColor: "#fff",
      borderColor: "#E5E7EB",
      textStyle: { color: "#374151", fontSize: 10, fontFamily: "monospace" },
      formatter: (params: Array<{ name: string; value: number; data: { listings: number } }>) => {
        const p = params[0]!;
        return `${p.name}<br/>SAR ${p.value.toLocaleString()} / sqm / yr<br/>${p.data.listings} listing${p.data.listings !== 1 ? "s" : ""}`;
      },
    },
    xAxis: {
      type: "value",
      axisLabel: {
        color: "#A3A3A3",
        fontSize: 9,
        formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v),
      },
      splitLine: { lineStyle: { color: "#F0F0F0" } },
      axisLine: { show: false },
    },
    yAxis: {
      type: "category",
      data: [...rows].reverse().map(r => r.district),
      axisLabel: { color: "#6B7280", fontSize: 9 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: [...rows].reverse().map(r => ({
          value: r.avgPerSqm,
          listings: r.listings,
          itemStyle: {
            color: r.avgPerSqm > 200
              ? "#002060"
              : r.avgPerSqm > 120
                ? "#1e40af"
                : "#93C5FD",
            borderRadius: [0, 2, 2, 0],
          },
        })),
        label: {
          show: true,
          position: "right",
          color: "#9CA3AF",
          fontSize: 9,
          fontFamily: "monospace",
          formatter: (p: { value: number }) =>
            `${p.value.toLocaleString()}`,
        },
        barMaxWidth: 18,
      },
    ],
  };

  return (
    <div>
      <div style={{
        fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: "var(--text-tertiary)",
        marginBottom: "4px",
      }}>
        Avg Asking Rent (SAR/sqm/yr) by District
      </div>
      <ReactECharts
        option={option}
        style={{ height: `${chartHeight}px`, width: "100%" }}
      />
    </div>
  );
}
