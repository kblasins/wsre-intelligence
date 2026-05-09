/**
 * Slim alert bar shown below the header when data quality issues are detected.
 */
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useJobs, usePipelineStatus } from "../hooks/useMarketData";

interface AdminHealth {
  status: "ok" | "degraded";
  db: string;
  open_circuit_breakers: string[];
  review_queue_pending: number;
}

function useAdminHealth() {
  return useQuery<AdminHealth>({
    queryKey: ["admin-health"],
    queryFn: () => api.get<AdminHealth>("/api/admin/health"),
    refetchInterval: 60_000,
  });
}

export function DataAlertBanner() {
  const { data: jobs } = useJobs();
  const { data: pipeline } = usePipelineStatus();
  const { data: health } = useAdminHealth();
  const navigate = useNavigate();

  const staleJobs    = jobs?.filter(j => j.is_enabled && j.stale) ?? [];
  const failedJobs   = jobs?.filter(j => j.is_enabled && j.consecutive_failures >= 3) ?? [];
  const permanentFail = pipeline?.outbox.permanently_failed ?? 0;
  const reviewPending = pipeline?.review_queue.pending_review ?? 0;
  const openBreakers  = health?.open_circuit_breakers ?? [];

  const alerts: string[] = [];
  if (staleJobs.length > 0)   alerts.push(`${staleJobs.length} source${staleJobs.length > 1 ? "s" : ""} stale: ${staleJobs.map(j => j.source_key).join(", ")}`);
  if (failedJobs.length > 0)  alerts.push(`${failedJobs.length} scraper${failedJobs.length > 1 ? "s" : ""} failing: ${failedJobs.map(j => j.source_key).join(", ")}`);
  if (permanentFail > 0)      alerts.push(`${permanentFail} outbox row${permanentFail > 1 ? "s" : ""} permanently failed`);
  if (openBreakers.length > 0) alerts.push(`circuit breaker${openBreakers.length > 1 ? "s" : ""} open: ${openBreakers.join(", ")}`);

  if (alerts.length === 0) return null;

  return (
    <div style={{
      background: "#FEF2F2",
      borderBottom: "1px solid #FECACA",
      padding: "6px 24px",
      display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap",
    }}>
      <span className="ws-upper" style={{ color: "var(--down)", flexShrink: 0 }}>
        Data Alert
      </span>

      <div style={{ flex: 1, display: "flex", flexWrap: "wrap", gap: "16px" }}>
        {alerts.map((a, i) => (
          <span key={i} style={{ fontSize: "12px", color: "#991B1B", fontFamily: "'IBM Plex Mono', monospace" }}>
            {a}
          </span>
        ))}
      </div>

      {reviewPending > 0 && (
        <span style={{ fontSize: "12px", color: "var(--warn)", fontVariantNumeric: "tabular-nums" }}>
          {reviewPending} extraction{reviewPending > 1 ? "s" : ""} need review
        </span>
      )}

      <button
        onClick={() => navigate("/admin")}
        className="btn"
        style={{ fontSize: "11px", color: "var(--down)", borderColor: "#FECACA", flexShrink: 0 }}
      >
        Admin →
      </button>
    </div>
  );
}
