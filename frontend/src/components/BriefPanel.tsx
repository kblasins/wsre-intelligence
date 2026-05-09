import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useLatestBrief } from "../hooks/useMarketData";
import type { BriefNewsItem, BriefWatchItem, BriefMacroItem } from "../types/api";

export function BriefPanel() {
  const { data: brief, isLoading, isError } = useLatestBrief();
  const qc = useQueryClient();
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  async function handleTrigger() {
    setTriggering(true);
    setTriggerMsg(null);
    try {
      await api.post("/api/briefs/trigger", {});
      setTriggerMsg("Brief generation started — check back in ~2 minutes.");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["brief-latest"] }), 120_000);
    } catch {
      setTriggerMsg("Could not trigger brief. Check API key configuration.");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div style={{ marginTop: "32px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid var(--border)",
      }}>
        <h3 className="ws-sub-h">Weekly Brief</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {brief && (
            <a
              href={`/api/briefs/${brief.id}/pdf`}
              target="_blank" rel="noopener noreferrer"
              className="btn ghost"
              style={{ fontSize: "11px" }}
            >
              ↓ PDF
            </a>
          )}
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="btn"
            style={{ fontSize: "12px" }}
          >
            {triggering ? "Generating…" : "Generate"}
          </button>
        </div>
      </div>

      {triggerMsg && (
        <div style={{
          marginBottom: "12px", padding: "10px 14px",
          background: "var(--bg-wash)", border: "1px solid var(--border)",
          fontSize: "13px", color: "var(--text-secondary)",
          borderLeft: "3px solid var(--brand-navy)",
        }}>
          {triggerMsg}
        </div>
      )}

      {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

      {!isLoading && (isError || !brief) && (
        <div className="empty-state">
          <p style={{ fontWeight: 500, marginBottom: "8px" }}>No brief generated yet.</p>
          <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", color: "var(--brand-navy)" }}>
            python -m app.briefing.orchestrator
          </code>
          <p className="ws-small" style={{ maxWidth: "360px", lineHeight: 1.6, marginTop: "6px" }}>
            Add ANTHROPIC_API_KEY to .env.local and run the command above.
          </p>
        </div>
      )}

      {brief && (
        <article className="brief-doc" style={{ animation: "fadeUp 0.4s ease both", maxWidth: "none" }}>
          {/* Meta strip */}
          <div className="brief-meta-strip">
            <span>Week ending {brief.week_ending}</span>
            <span className="dot">·</span>
            <span>{brief.model_id.replace("claude-", "")}</span>
            <span className="dot">·</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>${brief.cost_usd.toFixed(4)}</span>
            {brief.pdf_uri && (
              <>
                <span className="dot">·</span>
                <a href={`/api/briefs/${brief.id}/pdf`} target="_blank" rel="noopener noreferrer">
                  Download PDF
                </a>
              </>
            )}
          </div>

          {/* Executive summary */}
          {brief.brief_json.executive_summary && (
            <p style={{ fontSize: "16px", lineHeight: 1.7, fontStyle: "italic", marginBottom: "28px" }}>
              {brief.brief_json.executive_summary}
            </p>
          )}

          {/* Commentary sections */}
          {[
            { key: "reit_commentary",        heading: "Industrial REITs" },
            { key: "transaction_commentary", heading: "Transactions" },
            { key: "warehouse_commentary",   heading: "Warehouse Market" },
          ].map(({ key, heading }) => {
            const text = brief.brief_json[key as keyof typeof brief.brief_json];
            if (typeof text !== "string" || !text) return null;
            return (
              <div key={key}>
                <h2>{heading}</h2>
                <p>{text}</p>
              </div>
            );
          })}

          {/* News intelligence */}
          {brief.brief_json.news_intelligence && brief.brief_json.news_intelligence.length > 0 && (
            <div>
              <h2>News & Intelligence</h2>
              {brief.brief_json.news_intelligence.map((item: BriefNewsItem, i: number) => (
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
          {brief.brief_json.macro_highlights && brief.brief_json.macro_highlights.length > 0 && (
            <div>
              <h2>Macro Environment</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "1px", background: "var(--border)", marginBottom: "16px" }}>
                {brief.brief_json.macro_highlights.map((item: BriefMacroItem, i: number) => (
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
          {brief.brief_json.watch_list && brief.brief_json.watch_list.length > 0 && (
            <div>
              <h2>Watch List</h2>
              {brief.brief_json.watch_list.map((item: BriefWatchItem, i: number) => (
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

          {/* Footer */}
          <div style={{
            marginTop: "40px", paddingTop: "14px", borderTop: "1px solid var(--divider)",
            fontSize: "11px", color: "var(--text-tertiary)",
          }}>
            Strictly private &amp; confidential · WSRE Intelligence · Internal circulation only
          </div>
        </article>
      )}
    </div>
  );
}
