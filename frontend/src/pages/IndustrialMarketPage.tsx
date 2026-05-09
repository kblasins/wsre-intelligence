/**
 * IndustrialMarketPage — KPI overview, REIT grid, transactions, listings,
 * rent index, news, tenders, and briefs.
 *
 * Route: /industrial
 */

import { BriefPanel } from "../components/BriefPanel";
import { ListingsPanel } from "../components/ListingsPanel";
import { NewsFeed } from "../components/NewsFeed";
import { ReitGrid } from "../components/ReitGrid";
import { RentIndexPanel } from "../components/RentIndexPanel";
import { SystemStatus } from "../components/SystemStatus";
import { TransactionsPanel } from "../components/TransactionsPanel";
import { TendersPanel } from "../components/TendersPanel";
import { DataAlertBanner } from "../components/DataAlertBanner";
import { useStats } from "../hooks/useMarketData";

export function IndustrialMarketPage() {
  const { data: stats } = useStats();

  return (
    <div style={{ flex: 1, overflowY: "auto", background: "var(--bg-page)" }}>
      <DataAlertBanner />

      {/* KPI strip */}
      {stats && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(6, 1fr)",
          gap: "1px",
          background: "var(--border)",
          borderBottom: "1px solid var(--border)",
        }}>
          {[
            { label: "REITs",       value: stats.reit_snapshots },
            { label: "Transactions",value: stats.transactions   },
            { label: "Listings",    value: stats.listings       },
            { label: "News",        value: stats.news_articles  },
            { label: "Rent Index",  value: stats.rent_index     },
            { label: "Tenders",     value: stats.tenders        },
          ].map(({ label, value }) => (
            <div
              key={label}
              style={{
                background: "var(--bg-surface)",
                padding: "16px 20px",
              }}
            >
              <div className="label" style={{
                fontSize: "11px", textTransform: "uppercase",
                letterSpacing: "0.5px", color: "var(--text-secondary)",
                fontWeight: 500,
              }}>
                {label}
              </div>
              <div style={{
                fontSize: "24px", fontWeight: 500, color: "var(--text-primary)",
                fontVariantNumeric: "tabular-nums", marginTop: "4px",
                fontFamily: "'IBM Plex Mono', monospace",
              }}>
                {value?.toLocaleString() ?? "—"}
              </div>
            </div>
          ))}
        </div>
      )}

      <main style={{
        maxWidth: "1400px",
        margin: "0 auto",
        padding: "32px 32px 64px",
      }}>
        <ReitGrid />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "32px", alignItems: "start" }}>
          <TransactionsPanel />
          <ListingsPanel />
        </div>
        <RentIndexPanel />
        <NewsFeed />
        <TendersPanel />
        <BriefPanel />
        <SystemStatus />
      </main>
    </div>
  );
}
