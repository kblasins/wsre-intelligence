/**
 * IntelligencePage — filterable feed of all typed facts
 * extracted from news articles across 8 signal tables.
 *
 * Route: /intelligence
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface FactItem {
  id: number;
  table: string;
  created_at: string | null;
  confidence: number | null;
  source_citation: string | null;
  article_id: number | null;
  summary: string | null;
}

interface FactsResponse {
  total: number;
  items: FactItem[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const ALL_TABLES = [
  "supply_events",
  "regulatory_events",
  "macro_signals",
  "demand_signals",
  "capital_markets_events",
  "infrastructure_events",
  "tenant_signals",
  "market_commentary",
];

const TABLE_LABELS: Record<string, string> = {
  supply_events:           "Supply",
  regulatory_events:       "Regulatory",
  macro_signals:           "Macro",
  demand_signals:          "Demand",
  capital_markets_events:  "Capital Mkts",
  infrastructure_events:   "Infrastructure",
  tenant_signals:          "Tenant",
  market_commentary:       "Commentary",
};

const TABLE_PILL_CLASS: Record<string, string> = {
  supply_events:           "supply",
  regulatory_events:       "regulatory",
  macro_signals:           "macro",
  demand_signals:          "demand",
  capital_markets_events:  "capital",
  infrastructure_events:   "infra",
  tenant_signals:          "tenant",
  market_commentary:       "commentary",
};

const PAGE_SIZE = 50;

// ── Hook ──────────────────────────────────────────────────────────────────────

function useIntelligenceFacts(params: {
  table: string | null;
  minConfidence: number;
  q: string;
  offset: number;
}) {
  const searchParams = new URLSearchParams({
    min_confidence: String(params.minConfidence),
    limit: String(PAGE_SIZE),
    offset: String(params.offset),
  });
  if (params.table) searchParams.set("table", params.table);
  if (params.q) searchParams.set("q", params.q);

  return useQuery<FactsResponse>({
    queryKey: ["intelligence-facts", params],
    queryFn: () => api.get<FactsResponse>(`/api/intelligence/facts?${searchParams}`),
    placeholderData: (prev) => prev,
  });
}

// ── Components ────────────────────────────────────────────────────────────────

function ConfDots({ confidence }: { confidence: number | null }) {
  const c = Math.min(5, Math.max(0, Math.round(confidence ?? 0)));
  return (
    <span className="conf">
      {[1, 2, 3, 4, 5].map((i) => (
        <i key={i} className={i <= c ? "on" : ""} />
      ))}
    </span>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function IntelligencePage() {
  const [activeTable, setActiveTable] = useState<string | null>(null);
  const [minConfidence, setMinConfidence] = useState(4);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, isFetching } = useIntelligenceFacts({
    table: activeTable,
    minConfidence,
    q: debouncedQ,
    offset,
  });

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  function handleSearch(value: string) {
    setQ(value);
    clearTimeout((window as any)._iqTimer);
    (window as any)._iqTimer = setTimeout(() => {
      setDebouncedQ(value);
      setOffset(0);
    }, 300);
  }

  function handleTableFilter(tbl: string | null) {
    setActiveTable(tbl);
    setOffset(0);
  }

  function handleConfidence(val: number) {
    setMinConfidence(val);
    setOffset(0);
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", background: "var(--bg-page)" }}>
      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "24px 32px 64px" }}>

        {/* Page heading */}
        <div style={{ marginBottom: "20px", display: "flex", alignItems: "baseline", gap: "16px" }}>
          <h1 className="ws-page-title">Intelligence Feed</h1>
          <span className="ws-meta">
            {total.toLocaleString()} facts
            {isFetching && " · loading…"}
          </span>
        </div>

        {/* Filter bar */}
        <div style={{
          display: "flex", gap: "16px", alignItems: "center",
          flexWrap: "wrap", marginBottom: "16px",
          padding: "10px 16px",
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
        }}>
          {/* Search */}
          <input
            type="text"
            placeholder="Search citations…"
            value={q}
            onChange={(e) => handleSearch(e.target.value)}
            style={{
              background: "var(--bg-page)", border: "1px solid var(--border)",
              color: "var(--text-primary)", fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "12px", padding: "5px 10px",
              width: "220px", outline: "none", borderRadius: "3px",
            }}
          />

          {/* Confidence filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="ws-upper">Min conf.</span>
            {[1, 2, 3, 4, 5].map((c) => (
              <button
                key={c}
                onClick={() => handleConfidence(c)}
                style={{
                  background: minConfidence === c ? "var(--brand-navy)" : "#fff",
                  border: `1px solid ${minConfidence === c ? "var(--brand-navy)" : "var(--border)"}`,
                  color: minConfidence === c ? "#fff" : "var(--text-secondary)",
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "11px", width: "26px", height: "26px",
                  cursor: "pointer", borderRadius: "3px",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >
                {c}
              </button>
            ))}
          </div>

          {/* Table type filter */}
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            <button
              className={`chip${activeTable === null ? " active" : ""}`}
              onClick={() => handleTableFilter(null)}
            >
              All
            </button>
            {ALL_TABLES.map((tbl) => (
              <button
                key={tbl}
                className={`chip${activeTable === tbl ? " active" : ""}`}
                onClick={() => handleTableFilter(tbl)}
              >
                {TABLE_LABELS[tbl]}
              </button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="ws-card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="ws-table">
            <thead>
              <tr>
                <th style={{ width: "110px" }}>Date</th>
                <th style={{ width: "120px" }}>Type</th>
                <th style={{ width: "80px" }}>Conf.</th>
                <th>Summary &amp; Citation</th>
                <th style={{ width: "80px" }}>Article</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", color: "var(--text-tertiary)", padding: "32px 16px" }}>
                    No facts match the current filters.
                  </td>
                </tr>
              )}
              {items.map((item) => (
                <tr key={`${item.table}-${item.id}`}>
                  <td className="mono" style={{ color: "var(--text-secondary)", fontSize: "12px" }}>
                    {formatDate(item.created_at)}
                  </td>
                  <td>
                    <span className={`type-pill ${TABLE_PILL_CLASS[item.table] ?? ""}`}>
                      {TABLE_LABELS[item.table] ?? item.table}
                    </span>
                  </td>
                  <td>
                    <ConfDots confidence={item.confidence} />
                  </td>
                  <td>
                    {item.summary && (
                      <div style={{ fontSize: "13px", color: "var(--text-primary)", lineHeight: "1.4", marginBottom: item.source_citation ? "4px" : 0 }}>
                        {item.summary}
                      </div>
                    )}
                    {item.source_citation && (
                      <div style={{ fontSize: "11px", color: "var(--text-secondary)", fontStyle: "italic" }}>
                        "{item.source_citation}"
                      </div>
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>
                    {item.article_id ? `#${item.article_id}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="ws-table-pagination">
              <span>
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}
              </span>
              <div className="arrows">
                <button
                  className={`arr${offset === 0 ? " disabled" : ""}`}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  disabled={offset === 0}
                >
                  ‹
                </button>
                <span style={{ padding: "0 8px", lineHeight: "24px", fontSize: "12px" }}>
                  {currentPage} / {totalPages}
                </span>
                <button
                  className={`arr${offset + PAGE_SIZE >= total ? " disabled" : ""}`}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  disabled={offset + PAGE_SIZE >= total}
                >
                  ›
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
