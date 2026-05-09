/**
 * Briefs archive — lists all generated weekly briefs.
 * Each row can be expanded to read the full brief text.
 * Compare mode lets you select two briefs and view them side by side.
 */
import { useState } from "react";
import { useBrief, useBriefsList } from "../hooks/useMarketData";
import { formatDate } from "../lib/format";
import type { WeeklyBrief } from "../types/api";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: "8px", fontWeight: 700, letterSpacing: "0.16em",
      textTransform: "uppercase", color: "var(--brand-navy)", marginBottom: "8px",
    }}>
      {children}
    </div>
  );
}

export function BriefsPage() {
  const { data: briefs, isLoading } = useBriefsList();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState<number[]>([]);

  return (
    <div style={{ flex: 1, overflowY: "auto", background: "var(--bg-page)" }}>
      <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "32px 32px 80px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "16px", marginBottom: "8px" }}>
          <h1 className="ws-page-title">Intelligence Briefs</h1>
          <button
            onClick={() => {
              setCompareMode(v => !v);
              setCompareIds([]);
              setSelectedId(null);
            }}
            className={`btn${compareMode ? " primary" : ""}`}
            style={{ fontSize: "12px" }}
          >
            Compare
          </button>
        </div>
        <p style={{
          fontSize: "13px",
          color: "var(--text-secondary)",
          margin: "0 0 24px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
        }}>
          Weekly synthesis — Riyadh industrial real estate
          {compareMode && (
            <span style={{ color: "var(--brand-navy)" }}>
              {compareIds.length === 0
                ? "Select two briefs to compare"
                : compareIds.length === 1
                  ? "Select one more brief"
                  : "Comparing two briefs — scroll down"}
            </span>
          )}
        </p>

        {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

        {!isLoading && (!briefs || briefs.length === 0) && (
          <div className="empty-state">
            <p style={{ fontStyle: "italic", marginBottom: "8px" }}>No briefs yet.</p>
            <code style={{ fontSize: "12px", color: "var(--brand-navy)", fontFamily: "'IBM Plex Mono', monospace" }}>
              python -m app.briefing.orchestrator
            </code>
          </div>
        )}

        {briefs && briefs.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {briefs.map(brief => (
              <BriefRow
                key={brief.id}
                id={brief.id}
                weekEnding={brief.week_ending}
                summary={brief.executive_summary}
                generatedAt={brief.generated_at}
                costUsd={brief.cost_usd}
                modelId={brief.model_id}
                hasPdf={brief.has_pdf}
                compareMode={compareMode}
                isCompareSelected={compareIds.includes(brief.id)}
                isSelected={!compareMode && selectedId === brief.id}
                onSelect={() => {
                  if (compareMode) {
                    setCompareIds(prev => {
                      if (prev.includes(brief.id)) return prev.filter(id => id !== brief.id);
                      if (prev.length >= 2) return [prev[1]!, brief.id];
                      return [...prev, brief.id];
                    });
                  } else {
                    setSelectedId(selectedId === brief.id ? null : brief.id);
                  }
                }}
              />
            ))}
          </div>
        )}

        {/* ── Comparison view ──────────────────────────────────────────── */}
        {compareMode && compareIds.length === 2 && (
          <BriefComparison idA={compareIds[0]!} idB={compareIds[1]!} briefs={briefs ?? []} />
        )}
      </main>
    </div>
  );
}


function BriefRow({
  id, weekEnding, summary, generatedAt, costUsd, modelId, hasPdf,
  compareMode, isCompareSelected, isSelected, onSelect,
}: {
  id: number;
  weekEnding: string;
  summary: string;
  generatedAt: string;
  costUsd: number;
  modelId: string;
  hasPdf: boolean;
  compareMode: boolean;
  isCompareSelected: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { data: full } = useBrief(isSelected ? id : null);

  const weekLabel = new Date(weekEnding).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric",
  });

  const borderColor = isSelected || isCompareSelected
    ? "var(--brand-navy)"
    : "var(--border)";

  return (
    <div style={{
      background: isCompareSelected ? "rgba(201,146,42,0.05)" : "var(--bg-surface)",
      borderLeft: `2px solid ${borderColor}`,
      transition: "border-color 120ms ease",
    }}>
      {/* Row header — always visible */}
      <div
        onClick={onSelect}
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "20px",
          padding: "16px 20px",
          cursor: "pointer",
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLDivElement).style.background = "var(--bg-hover)";
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLDivElement).style.background = "transparent";
        }}
      >
        {/* Date column */}
        <div style={{ flexShrink: 0, width: "140px" }}>
          <div style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "12px",
            color: "var(--text-primary)",
            fontWeight: 600,
          }}>
            {weekLabel}
          </div>
          <div style={{ fontSize: "10px", color: "var(--text-tertiary)", marginTop: "2px" }}>
            {formatDate(generatedAt)}
          </div>
        </div>

        {/* Summary */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
            fontStyle: "italic",
            fontSize: "14px",
            color: "var(--text-secondary)",
            lineHeight: 1.5,
            margin: 0,
            display: "-webkit-box",
            WebkitLineClamp: isSelected ? "unset" : 2,
            WebkitBoxOrient: "vertical",
            overflow: isSelected ? "visible" : "hidden",
          }}>
            {summary || "(no summary)"}
          </p>
        </div>

        {/* Meta */}
        <div style={{ flexShrink: 0, textAlign: "right" }}>
          <div style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "10px",
            color: "var(--text-tertiary)",
          }}>
            ${costUsd.toFixed(4)}
          </div>
          <div style={{ fontSize: "9px", color: "var(--text-tertiary)", marginTop: "2px" }}>
            {modelId.replace("claude-", "")}
          </div>
          {hasPdf && (
            <a
              href={`/api/briefs/${id}/pdf`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                display: "block",
                marginTop: "4px",
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "0.1em",
                color: "var(--brand-navy)",
                textTransform: "uppercase",
                textDecoration: "none",
              }}
            >
              ↓ PDF
            </a>
          )}
        </div>

        {/* Expand chevron / compare indicator */}
        <div style={{
          flexShrink: 0,
          width: "16px",
          color: isCompareSelected ? "var(--brand-navy)" : "var(--text-tertiary)",
          fontSize: "12px",
          paddingTop: "2px",
          fontWeight: isCompareSelected ? 700 : 400,
        }}>
          {compareMode
            ? (isCompareSelected ? "✓" : "○")
            : (isSelected ? "▲" : "▼")}
        </div>
      </div>

      {/* Expanded full brief */}
      {isSelected && full && (
        <div style={{
          borderTop: "1px solid var(--border)",
          padding: "24px 20px 28px",
        }}>
          <BriefSections brief={full} />
        </div>
      )}
    </div>
  );
}

// Only string fields are comparable side-by-side
const COMPARE_SECTIONS: Array<{ key: string; label: string }> = [
  { key: "executive_summary",       label: "Executive Summary" },
  { key: "reit_commentary",         label: "Industrial REITs" },
  { key: "transaction_commentary",  label: "Transactions" },
  { key: "warehouse_commentary",    label: "Warehouse Market" },
];

function BriefComparison({
  idA, idB, briefs,
}: {
  idA: number;
  idB: number;
  briefs: Array<{ id: number; week_ending: string }>;
}) {
  const { data: briefA } = useBrief(idA);
  const { data: briefB } = useBrief(idB);

  const metaA = briefs.find(b => b.id === idA);
  const metaB = briefs.find(b => b.id === idB);

  function weekLabel(iso: string) {
    return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }

  return (
    <div style={{ marginTop: "32px", animation: "fadeUp 0.3s ease both" }}>
      <div style={{
        fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
        textTransform: "uppercase", color: "var(--text-tertiary)",
        marginBottom: "16px",
        paddingBottom: "8px",
        borderBottom: "1px solid var(--border)",
      }}>
        Comparison
      </div>

      {/* Column headers */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "8px" }}>
        {[{ meta: metaA, label: "A" }, { meta: metaB, label: "B" }].map(({ meta, label }) => (
          <div key={label} style={{
            padding: "8px 12px",
            background: "var(--bg-surface)",
            borderLeft: "2px solid var(--brand-navy)",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "11px",
            color: "var(--brand-navy)",
          }}>
            {meta ? weekLabel(meta.week_ending) : "…"}
          </div>
        ))}
      </div>

      {(!briefA || !briefB) && (
        <div style={{
          padding: "24px",
          textAlign: "center",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "11px",
          color: "var(--text-tertiary)",
        }}>
          Loading briefs…
        </div>
      )}

      {briefA && briefB && COMPARE_SECTIONS.map(({ key, label }) => {
        type BriefKey = keyof typeof briefA.brief_json;
        const textA = briefA.brief_json[key as BriefKey];
        const textB = briefB.brief_json[key as BriefKey];
        // Only render string fields in comparison
        const strA = typeof textA === "string" ? textA : null;
        const strB = typeof textB === "string" ? textB : null;
        if (!strA && !strB) return null;
        return (
          <div key={key} style={{ marginBottom: "12px" }}>
            <div style={{
              fontSize: "8px", fontWeight: 700, letterSpacing: "0.14em",
              textTransform: "uppercase", color: "var(--text-tertiary)",
              marginBottom: "4px", padding: "0 2px",
            }}>
              {label}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              {[strA, strB].map((text, i) => (
                <div key={i} style={{
                  padding: "14px 16px",
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  fontSize: "12px",
                  color: text ? "var(--text-secondary)" : "var(--text-tertiary)",
                  lineHeight: 1.65,
                  whiteSpace: "pre-wrap",
                  ...(key === "executive_summary" ? {
                    fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
                    fontStyle: "italic",
                    fontSize: "14px",
                    color: "var(--text-primary)",
                  } : {}),
                }}>
                  {text ?? "(no data)"}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BriefSections({ brief }: { brief: { brief_json: WeeklyBrief["brief_json"]; brief_text: string } }) {
  const [showRaw, setShowRaw] = useState(false);
  const j = brief.brief_json;

  const textSections: Array<{ key: keyof typeof j; label: string }> = [
    { key: "reit_commentary",        label: "Industrial REITs" },
    { key: "transaction_commentary", label: "Transactions" },
    { key: "warehouse_commentary",   label: "Warehouse Market" },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}>
        <button
          onClick={() => setShowRaw(v => !v)}
          style={{
            background: "transparent",
            border: "1px solid var(--border)",
            color: "var(--text-tertiary)",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "9px",
            letterSpacing: "0.1em",
            padding: "3px 8px",
            cursor: "pointer",
            textTransform: "uppercase",
          }}
        >
          {showRaw ? "Sections" : "Raw JSON"}
        </button>
      </div>

      {showRaw ? (
        <pre style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "11px",
          color: "var(--text-secondary)",
          whiteSpace: "pre-wrap",
          lineHeight: 1.7,
          margin: 0,
          background: "var(--bg-page)",
          padding: "16px",
          border: "1px solid var(--border)",
          maxHeight: "600px",
          overflowY: "auto",
        }}>
          {brief.brief_text}
        </pre>
      ) : (
        <article className="brief-doc" style={{ maxWidth: "none" }}>
          {/* Executive summary */}
          {j.executive_summary && (
            <p style={{ fontSize: "16px", lineHeight: 1.7, fontStyle: "italic", marginBottom: "28px" }}>
              {j.executive_summary}
            </p>
          )}

          {/* Commentary sections */}
          {textSections.map(({ key, label }) => {
            const text = j[key];
            if (typeof text !== "string" || !text) return null;
            return (
              <div key={key as string}>
                <h2>{label}</h2>
                <p>{text}</p>
              </div>
            );
          })}

          {/* News intelligence */}
          {j.news_intelligence && j.news_intelligence.length > 0 && (
            <div>
              <h2>News & Intelligence</h2>
              {j.news_intelligence.map((item, i) => (
                <div key={i} style={{ marginBottom: "20px" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginBottom: "4px" }}>
                    <span style={{
                      fontFamily: "'IBM Plex Mono', monospace", fontSize: "11px", fontWeight: 600,
                      color: item.score >= 8 ? "var(--up)" : item.score >= 5 ? "var(--warn)" : "var(--text-tertiary)",
                      minWidth: "20px",
                    }}>
                      {item.score}
                    </span>
                    <strong style={{ fontSize: "14px", fontWeight: 500 }}>{item.headline}</strong>
                  </div>
                  <p style={{ marginLeft: "28px", marginBottom: "6px", color: "var(--text-secondary)" }}>
                    {item.implication}
                  </p>
                  {item.citation && (
                    <blockquote style={{ marginLeft: "28px" }}>
                      {item.citation}
                      <span className="attr">— {item.source}{item.date ? `, ${item.date}` : ""}</span>
                    </blockquote>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Macro highlights */}
          {j.macro_highlights && j.macro_highlights.length > 0 && (
            <div>
              <h2>Macro Environment</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "1px", background: "var(--border)", marginBottom: "16px" }}>
                {j.macro_highlights.map((item, i) => (
                  <div key={i} style={{ background: "var(--bg-surface)", padding: "12px 16px" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "5px" }}>
                      <span style={{
                        fontFamily: "'IBM Plex Mono', monospace", fontSize: "18px", fontWeight: 500,
                        fontVariantNumeric: "tabular-nums", color: "var(--text-primary)",
                      }}>
                        {item.value}
                      </span>
                      <span style={{ fontSize: "10px", color: item.direction === "up" ? "var(--up)" : item.direction === "down" ? "var(--down)" : "var(--text-tertiary)" }}>
                        {item.direction === "up" ? "▲" : item.direction === "down" ? "▼" : "—"}
                      </span>
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "3px" }}>{item.indicator}</div>
                    <div style={{ fontSize: "10px", color: "var(--text-tertiary)" }}>{item.period}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Watch list */}
          {j.watch_list && j.watch_list.length > 0 && (
            <div>
              <h2>Watch List</h2>
              {j.watch_list.map((item, i) => (
                <div key={i} style={{
                  marginBottom: "16px", padding: "14px 18px",
                  borderLeft: "2px solid var(--brand-navy)",
                  background: "var(--bg-surface)",
                }}>
                  <div style={{ fontSize: "14px", fontWeight: 500, marginBottom: "6px" }}>{item.item}</div>
                  <p style={{ margin: "0 0 4px", color: "var(--text-secondary)", fontSize: "13px" }}>
                    <span style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Trigger: </span>
                    {item.trigger}
                  </p>
                  <div style={{ fontSize: "11px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
                    {item.timeline}
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      )}
    </div>
  );
}
