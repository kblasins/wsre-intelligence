import { usePipelineStatus } from "../hooks/useMarketData";

/**
 * Compact pipeline health strip shown at the bottom of the dashboard.
 */
export function SystemStatus() {
  const { data: pipeline } = usePipelineStatus();

  if (!pipeline) return null;

  const items: Array<{ label: string; value: number; warn: boolean }> = [
    { label: "outbox pending",   value: pipeline.outbox.pending,                  warn: pipeline.outbox.pending > 20 },
    { label: "outbox failed",    value: pipeline.outbox.permanently_failed,        warn: pipeline.outbox.permanently_failed > 0 },
    { label: "triage backlog",   value: pipeline.news.triage_backlog,              warn: pipeline.news.triage_backlog > 100 },
    { label: "body fetch",       value: pipeline.news.body_fetching_backlog,        warn: pipeline.news.body_fetching_backlog > 50 },
    { label: "extraction",       value: pipeline.news.extraction_backlog,           warn: pipeline.news.extraction_backlog > 50 },
    { label: "review queue",     value: pipeline.review_queue.pending_review,       warn: pipeline.review_queue.pending_review > 0 },
  ];

  const hasWarnings = items.some((i) => i.warn);

  return (
    <div style={{
      marginTop: "40px",
      padding: "10px 16px",
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: "24px", flexWrap: "wrap",
    }}>
      <span className="ws-upper" style={{ color: hasWarnings ? "var(--down)" : "var(--text-tertiary)", flexShrink: 0 }}>
        Pipeline
      </span>

      {items.map(({ label, value, warn }) => (
        <span key={label} style={{
          fontSize: "12px", display: "flex", gap: "5px",
          fontVariantNumeric: "tabular-nums",
          color: warn ? "var(--down)" : "var(--text-tertiary)",
        }}>
          <span style={{
            fontFamily: "'IBM Plex Mono', monospace",
            color: warn ? "var(--down)" : "var(--text-primary)",
            fontWeight: warn ? 600 : 400,
          }}>
            {value}
          </span>
          {label}
        </span>
      ))}
    </div>
  );
}
