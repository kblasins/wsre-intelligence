/**
 * Government tenders panel — shows Etimad tenders relevant to
 * the industrial / warehouse sector in Saudi Arabia.
 */
import { useTenders } from "../hooks/useMarketData";
import { formatDate } from "../lib/format";
import type { Tender } from "../types/api";

function fmtSAR(v: number): string {
  if (v >= 1_000_000_000) return `SAR ${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `SAR ${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `SAR ${(v / 1_000).toFixed(0)}K`;
  return `SAR ${v.toLocaleString("en-US")}`;
}

function daysUntil(isoDate: string | null): number | null {
  if (!isoDate) return null;
  const deadline = new Date(isoDate).getTime();
  const now = Date.now();
  return Math.ceil((deadline - now) / 86_400_000);
}

export function TendersPanel() {
  const { data: tenders, isLoading } = useTenders(50);

  return (
    <div style={{ marginTop: "32px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid var(--border)",
      }}>
        <h3 className="ws-sub-h">Etimad Tenders</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {tenders && tenders.length > 0 && (
            <span className="ws-small" style={{ fontVariantNumeric: "tabular-nums" }}>
              {tenders.length} active
            </span>
          )}
          <a
            href="/api/tenders/export.csv"
            download="tenders.csv"
            className="btn ghost"
            style={{ fontSize: "11px", textDecoration: "none" }}
          >
            ↓ CSV
          </a>
        </div>
      </div>

      {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

      {!isLoading && (!tenders || tenders.length === 0) && (
        <div className="empty-state">
          <p style={{ marginBottom: "8px", fontWeight: 500 }}>No tender data yet.</p>
          <p className="ws-small" style={{ lineHeight: 1.6 }}>
            Configure{" "}
            <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--brand-navy)" }}>ETIMAD_CLIENT_ID</code>
            {" "}and{" "}
            <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--brand-navy)" }}>ETIMAD_CLIENT_SECRET</code>
            {" "}in .env.local
          </p>
        </div>
      )}

      {tenders && tenders.length > 0 && (
        <div className="ws-card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="ws-table">
            <thead>
              <tr>
                <th className="num" style={{ width: "100px" }}>Value</th>
                <th>Title</th>
                <th>Entity</th>
                <th style={{ width: "90px" }}>Published</th>
                <th style={{ width: "80px" }}>Deadline</th>
              </tr>
            </thead>
            <tbody>
              {tenders.map((tender, i) => (
                <TenderRow key={tender.id} tender={tender} index={i} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TenderRow({ tender, index }: { tender: Tender; index: number }) {
  const titleEn = tender.title_en ?? tender.title_ar ?? "(no title)";
  const days = daysUntil(tender.deadline_at);

  const deadlineColor =
    days === null ? "var(--text-tertiary)"
    : days < 3   ? "var(--down)"
    : days < 7   ? "#B45309"
    : "var(--text-secondary)";

  return (
    <tr className="fade-up" style={{ animationDelay: `${index * 25}ms` }}>
      <td className="num" style={{ fontFamily: "'IBM Plex Mono', monospace", fontWeight: 500, color: "var(--brand-navy)", whiteSpace: "nowrap" }}>
        {tender.value_sar != null ? fmtSAR(tender.value_sar) : "—"}
      </td>
      <td>
        <div style={{ fontSize: "13px", color: "var(--text-primary)", lineHeight: 1.4, marginBottom: tender.title_ar && tender.title_en ? "3px" : 0 }}>
          {titleEn}
        </div>
        {tender.title_ar && tender.title_en && (
          <div style={{
            fontSize: "12px", color: "var(--text-secondary)",
            direction: "rtl", fontFamily: "'IBM Plex Sans Arabic', sans-serif",
          }}>
            {tender.title_ar}
          </div>
        )}
      </td>
      <td>
        {tender.entity_name && (
          <span className="type-pill">{tender.entity_name}</span>
        )}
      </td>
      <td style={{ fontSize: "12px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
        {tender.published_at ? formatDate(tender.published_at) : "—"}
      </td>
      <td style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", color: deadlineColor, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
        {days !== null
          ? days > 0 ? `${days}d left`
          : days === 0 ? "today"
          : "closed"
          : "—"}
      </td>
    </tr>
  );
}
