/**
 * Full article detail modal — shows body text, structured facts, and market signal.
 * Opens when a NewsFeed row is clicked.
 */
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

interface ArticleDetail {
  id: number;
  source: string;
  title_en: string | null;
  title_ar: string | null;
  url: string | null;
  published_at: string | null;
  relevance_score: number | null;
  body_en: string | null;
  body_ar: string | null;
  structured_facts: Record<string, unknown>;
  model_id: string | null;
  confidence: number | null;
}

interface Props {
  articleId: number;
  onClose: () => void;
}

function useArticleDetail(id: number) {
  return useQuery<ArticleDetail>({
    queryKey: ["news-detail", id],
    queryFn: () => api.get<ArticleDetail>(`/api/news/${id}`),
    staleTime: Infinity,
  });
}

export function NewsArticleModal({ articleId, onClose }: Props) {
  const { data: article, isLoading } = useArticleDetail(articleId);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const facts = article?.structured_facts;
  const hasFacts = typeof facts === "object" && facts !== null && Object.keys(facts).length > 0;
  const signal = hasFacts ? (facts.market_signal as string | null) : null;
  const rentMovements = hasFacts ? (facts.rent_movements as Array<Record<string, unknown>> | null) : null;
  const keyEntities = hasFacts ? (facts.key_entities as string[] | null) : null;
  const supplyAdditions = hasFacts ? (facts.supply_additions as Array<Record<string, unknown>> | null) : null;
  const transactions = hasFacts ? (facts.transactions as Array<Record<string, unknown>> | null) : null;
  // Collect any remaining fact keys for generic display
  const knownKeys = new Set(["market_signal", "rent_movements", "key_entities", "supply_additions", "transactions"]);
  const extraFacts = hasFacts
    ? Object.entries(facts).filter(([k]) => !knownKeys.has(k))
    : [];

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        padding: "40px 16px",
        overflowY: "auto",
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        width: "100%", maxWidth: "720px",
        background: "var(--color-bg-surface)",
        border: "1px solid var(--color-border-subtle)",
        padding: "32px",
        position: "relative",
      }}>
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute", top: "16px", right: "16px",
            background: "transparent", border: "none",
            color: "var(--color-text-tertiary)",
            fontSize: "18px", cursor: "pointer", lineHeight: 1,
          }}
        >
          ×
        </button>

        {isLoading && (
          <div style={{ color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
            Loading…
          </div>
        )}

        {article && (
          <>
            {/* Source + score pill */}
            <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "16px" }}>
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: "9px",
                color: "var(--color-accent)", border: "1px solid var(--color-accent)",
                padding: "2px 6px", textTransform: "uppercase", letterSpacing: "0.08em",
              }}>
                {article.source}
              </span>
              {article.relevance_score != null && (
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: "9px",
                  color: "var(--color-text-tertiary)",
                }}>
                  relevance {article.relevance_score.toFixed(2)}
                </span>
              )}
              {article.confidence != null && (
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: "9px",
                  color: article.confidence <= 2 ? "#f87171" : "var(--color-text-tertiary)",
                }}>
                  confidence {article.confidence}/5
                </span>
              )}
            </div>

            {/* Title */}
            <h2 style={{
              fontFamily: "var(--font-display)", fontSize: "20px",
              fontWeight: 400, fontStyle: "italic",
              color: "var(--color-text-primary)",
              marginBottom: "8px", lineHeight: 1.3,
            }}>
              {article.title_en || article.title_ar || "(no title)"}
            </h2>

            {article.title_ar && article.title_en && (
              <p style={{
                fontFamily: "var(--font-mono)", fontSize: "12px",
                color: "var(--color-text-tertiary)",
                direction: "rtl", marginBottom: "12px",
              }}>
                {article.title_ar}
              </p>
            )}

            <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", marginBottom: "20px" }}>
              {article.published_at
                ? new Date(article.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
                : "Date unknown"}
              {article.url && (
                <> · <a href={article.url} target="_blank" rel="noopener noreferrer"
                  style={{ color: "var(--color-accent)" }}>Original article ↗</a></>
              )}
            </div>

            {/* Market signal */}
            {signal && (
              <div style={{
                padding: "12px 16px", marginBottom: "20px",
                borderLeft: "3px solid var(--color-accent)",
                background: "rgba(201,146,42,0.05)",
                fontSize: "13px", color: "var(--color-text-secondary)",
                lineHeight: 1.5,
              }}>
                {signal}
              </div>
            )}

            {/* Body text */}
            {(article.body_en || article.body_ar) && (
              <div style={{ marginBottom: "20px" }}>
                <div style={sectionLabel}>Article Body</div>
                <p style={{
                  fontSize: "13px", color: "var(--color-text-secondary)",
                  lineHeight: 1.7, whiteSpace: "pre-wrap",
                  maxHeight: "300px", overflowY: "auto",
                  direction: article.body_en ? "ltr" : "rtl",
                }}>
                  {article.body_en || article.body_ar}
                </p>
              </div>
            )}

            {!article.body_en && !article.body_ar && (
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: "10px",
                color: "var(--color-text-tertiary)", marginBottom: "20px",
              }}>
                Body not yet fetched. Will be populated by the next body-fetch run.
              </div>
            )}

            {/* Rent movements */}
            {rentMovements && rentMovements.length > 0 && (
              <div style={{ marginBottom: "20px" }}>
                <div style={sectionLabel}>Extracted Rent Movements</div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                  <thead>
                    <tr>
                      {["District", "Type", "Direction", "Change %", "Period"].map(h => (
                        <th key={h} style={{ ...thStyle }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rentMovements.map((mv, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                        <td style={tdStyle}>{(mv.district as string) || "—"}</td>
                        <td style={tdStyle}>{(mv.property_type as string) || "—"}</td>
                        <td style={{
                          ...tdStyle,
                          color: mv.direction === "up" ? "#4ade80" : mv.direction === "down" ? "#f87171" : "var(--color-text-secondary)",
                          fontWeight: 600,
                        }}>
                          {(mv.direction as string) || "—"}
                        </td>
                        <td style={{ ...tdStyle, fontVariantNumeric: "tabular-nums" }}>
                          {mv.change_pct != null ? `${mv.change_pct}%` : "—"}
                        </td>
                        <td style={tdStyle}>{(mv.period as string) || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Transactions extracted */}
            {transactions && transactions.length > 0 && (
              <div style={{ marginBottom: "20px" }}>
                <div style={sectionLabel}>Extracted Transactions</div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                  <thead>
                    <tr>
                      {["District", "Type", "Area sqm", "Price SAR", "Period"].map(h => (
                        <th key={h} style={thStyle}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((tx, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                        <td style={tdStyle}>{String(tx.district ?? "—")}</td>
                        <td style={tdStyle}>{String(tx.property_type ?? "—")}</td>
                        <td style={{ ...tdStyle, fontVariantNumeric: "tabular-nums" }}>
                          {tx.area_sqm != null ? Number(tx.area_sqm).toLocaleString() : "—"}
                        </td>
                        <td style={{ ...tdStyle, fontVariantNumeric: "tabular-nums" }}>
                          {tx.price_sar != null ? `SAR ${Number(tx.price_sar).toLocaleString()}` : "—"}
                        </td>
                        <td style={tdStyle}>{String(tx.period ?? "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Supply additions */}
            {supplyAdditions && supplyAdditions.length > 0 && (
              <div style={{ marginBottom: "20px" }}>
                <div style={sectionLabel}>Supply Additions</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  {supplyAdditions.map((s, i) => (
                    <div key={i} style={{
                      padding: "8px 12px",
                      background: "var(--color-bg-canvas)",
                      border: "1px solid var(--color-border-subtle)",
                      fontSize: "11px",
                      color: "var(--color-text-secondary)",
                    }}>
                      {Object.entries(s).map(([k, v]) => (
                        <span key={k} style={{ marginRight: "12px" }}>
                          <span style={{ color: "var(--color-text-tertiary)", fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.08em" }}>{k}: </span>
                          {String(v)}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key entities */}
            {keyEntities && keyEntities.length > 0 && (
              <div style={{ marginBottom: "20px" }}>
                <div style={sectionLabel}>Key Entities</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {keyEntities.map((e, i) => (
                    <span key={i} style={{
                      fontFamily: "var(--font-mono)", fontSize: "10px",
                      color: "var(--color-text-secondary)",
                      border: "1px solid var(--color-border-subtle)",
                      padding: "2px 8px",
                    }}>
                      {e}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Extra / unknown fact keys */}
            {extraFacts.length > 0 && (
              <div style={{ marginBottom: "20px" }}>
                <div style={sectionLabel}>Additional Facts</div>
                <pre style={{
                  fontFamily: "var(--font-mono)", fontSize: "10px",
                  color: "var(--color-text-secondary)",
                  background: "var(--color-bg-canvas)",
                  border: "1px solid var(--color-border-subtle)",
                  padding: "12px",
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                  margin: 0,
                }}>
                  {JSON.stringify(Object.fromEntries(extraFacts), null, 2)}
                </pre>
              </div>
            )}

            {/* Model info */}
            {article.model_id && (
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: "9px",
                color: "var(--color-text-tertiary)",
                borderTop: "1px solid var(--color-border-subtle)", paddingTop: "12px",
              }}>
                Extracted by {article.model_id}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const sectionLabel: React.CSSProperties = {
  fontSize: "8px", fontWeight: 700, letterSpacing: "0.16em",
  textTransform: "uppercase", color: "var(--color-text-tertiary)",
  marginBottom: "8px",
};

const thStyle: React.CSSProperties = {
  padding: "6px 8px", textAlign: "left", fontSize: "8px",
  fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
  color: "var(--color-text-tertiary)", borderBottom: "1px solid var(--color-border-subtle)",
};

const tdStyle: React.CSSProperties = {
  padding: "8px", color: "var(--color-text-secondary)",
};
