import { useStats } from "../hooks/useMarketData";

export function StatsBar() {
  const { data: stats } = useStats();

  const items = [
    { label: "REIT snapshots", value: stats?.reit_snapshots ?? "—" },
    { label: "Transactions", value: stats?.transactions ?? "—" },
    { label: "Listings", value: stats?.listings ?? "—" },
    { label: "News articles", value: stats?.news_articles ?? "—" },
    { label: "Rent index", value: stats?.rent_index ?? "—" },
    { label: "Tenders", value: stats?.tenders ?? "—" },
  ];

  return (
    <div
      style={{
        display: "flex",
        gap: "24px",
        padding: "8px 0",
        borderBottom: "1px solid var(--color-border-subtle)",
        marginBottom: "24px",
      }}
    >
      {items.map((item) => (
        <span
          key={item.label}
          style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}
        >
          <span
            className="tabular-nums"
            style={{
              color: "var(--color-text-secondary)",
              fontWeight: 500,
              marginRight: "4px",
            }}
          >
            {typeof item.value === "number"
              ? item.value.toLocaleString()
              : item.value}
          </span>
          {item.label}
        </span>
      ))}
    </div>
  );
}
