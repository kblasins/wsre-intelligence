import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Transaction } from "../types/api";
import { useTransactionAggregate } from "../hooks/useMarketData";
import { TransactionBarChart } from "./charts/TransactionBarChart";
import { TransactionMonthlyChart } from "./charts/TransactionMonthlyChart";

function useTransactions() {
  return useQuery<Transaction[]>({
    queryKey: ["transactions"],
    queryFn: () => api.get<Transaction[]>("/api/transactions?limit=200"),
    refetchInterval: 30 * 60_000,
  });
}

function fmt(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString("en-US");
}

const TYPE_LABELS: Record<string, string> = {
  warehouse: "Warehouse",
  industrial_land: "Industrial Land",
  factory: "Factory",
  logistics: "Logistics",
  other: "Other",
};

export function TransactionsPanel() {
  const { data: txns, isLoading } = useTransactions();
  const { data: aggregate } = useTransactionAggregate();

  const byType: Record<string, Transaction[]> = {};
  for (const t of txns ?? []) {
    (byType[t.property_type] ??= []).push(t);
  }

  const typeOrder = ["warehouse", "industrial_land", "factory", "logistics", "other"];
  const sorted = Object.entries(byType).sort(
    (a, b) => typeOrder.indexOf(a[0]) - typeOrder.indexOf(b[0])
  );

  return (
    <div style={{ marginTop: "32px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid var(--border)",
      }}>
        <h3 className="ws-sub-h">REGA Transactions</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {txns && txns.length > 0 && (
            <span className="ws-small" style={{ fontVariantNumeric: "tabular-nums" }}>
              {txns.length} records
            </span>
          )}
          <a
            href="/api/transactions/export.csv"
            download="transactions.csv"
            className="btn ghost"
            style={{ fontSize: "11px", textDecoration: "none" }}
          >
            ↓ CSV
          </a>
        </div>
      </div>

      {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

      {!isLoading && txns?.length === 0 && (
        <div className="empty-state">
          <p style={{ marginBottom: "8px", fontWeight: 500 }}>No transaction data yet.</p>
          <p className="ws-small" style={{ maxWidth: "420px", lineHeight: 1.6 }}>
            REGA scraper requires DevTools XHR capture. Open srem.moj.gov.sa → filter Riyadh industrial → capture XHR.
          </p>
        </div>
      )}

      {txns && txns.length > 0 && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
          gap: "1px",
          background: "var(--border)",
          animation: "fadeUp 0.4s ease both",
        }}>
          {sorted.map(([ptype, rows]) => {
            const total = rows.reduce((s, r) => s + (r.price_sar ?? 0), 0);
            const areas = rows.map(r => r.area_sqm).filter((v): v is number => v != null);
            const avgArea = areas.length ? areas.reduce((a, b) => a + b, 0) / areas.length : null;
            return (
              <div key={ptype} style={{ background: "var(--bg-surface)", padding: "16px 20px" }}>
                <div className="label" style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.4px", color: "var(--text-secondary)", fontWeight: 500, marginBottom: "8px" }}>
                  {TYPE_LABELS[ptype] ?? ptype.replace("_", " ")}
                </div>
                <div style={{
                  fontSize: "28px", fontWeight: 500, color: "var(--text-primary)",
                  fontVariantNumeric: "tabular-nums", lineHeight: 1.1, marginBottom: "4px",
                  fontFamily: "'IBM Plex Mono', monospace",
                }}>
                  {rows.length}
                </div>
                <div className="ws-small" style={{ marginBottom: "8px" }}>transactions</div>
                <div style={{ fontSize: "13px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                  SAR {fmt(total)}
                </div>
                {avgArea != null && (
                  <div className="ws-small" style={{ fontVariantNumeric: "tabular-nums", marginTop: "2px" }}>
                    avg {fmt(avgArea)} sqm
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <TransactionBarChart />
      {aggregate && aggregate.length >= 2 && <TransactionMonthlyChart data={aggregate} />}
    </div>
  );
}
