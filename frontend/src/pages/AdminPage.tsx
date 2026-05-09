/**
 * Admin page — review queue for low-confidence LLM extractions.
 * Analysts can approve, reject, or mark items as golden set examples.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { useJobs, useSchedule, useCircuitBreakers, useFailedOutbox, useBudgetHistory, useBudgetStatus, useLLMCalls, useBudgetByTask, useAdminDistricts } from "../hooks/useMarketData";
import type { JobStatus, ScheduleEntry, CircuitBreakerStatus, FailedOutboxRow, LLMCallRow, TaskBreakdown, DistrictGroup } from "../hooks/useMarketData";
import { BudgetSparkline } from "../components/charts/BudgetSparkline";

interface ReviewItem {
  id: number;
  source_table: string;
  source_row_id: number;
  confidence: number | null;
  uncertain_fields: string[];
  llm_output: Record<string, unknown>;
  model_id: string | null;
  is_golden: boolean;
  created_at: string;
}

function useReviewQueue(pendingOnly = true) {
  return useQuery<ReviewItem[]>({
    queryKey: ["review-queue", pendingOnly],
    queryFn: () =>
      api.get<ReviewItem[]>(`/api/admin/review-queue?pending_only=${pendingOnly}&limit=50`),
    refetchInterval: 60_000,
  });
}

export function AdminPage() {
  const [pendingOnly, setPendingOnly] = useState(true);
  const { data: items, isLoading } = useReviewQueue(pendingOnly);
  const { data: jobs } = useJobs();
  const { data: schedule } = useSchedule();
  const { data: breakers } = useCircuitBreakers();
  const { data: failedOutbox } = useFailedOutbox();
  const { data: budgetHistory } = useBudgetHistory(14);
  const { data: budget } = useBudgetStatus();
  const { data: llmCalls } = useLLMCalls(100);
  const { data: budgetByTask } = useBudgetByTask(7);
  const [districtCity, setDistrictCity] = useState("");
  const { data: districts } = useAdminDistricts(districtCity || undefined);
  const [newAlias, setNewAlias] = useState("");
  const [newAliasLang, setNewAliasLang] = useState("en");
  const [newAliasDistrictId, setNewAliasDistrictId] = useState<number | null>(null);
  const [aliasMsg, setAliasMsg] = useState<string | null>(null);
  const qc = useQueryClient();
  const [briefDate, setBriefDate] = useState("");
  const [briefMsg, setBriefMsg] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importSource, setImportSource] = useState("manual_import");

  async function addAlias() {
    if (!newAliasDistrictId || !newAlias.trim()) return;
    await api.post("/api/admin/districts", {
      canonical_id: newAliasDistrictId,
      alias: newAlias.trim(),
      lang: newAliasLang,
    });
    setNewAlias("");
    setNewAliasDistrictId(null);
    setAliasMsg("Alias added.");
    qc.invalidateQueries({ queryKey: ["admin-districts"] });
    setTimeout(() => setAliasMsg(null), 4000);
  }

  async function triggerBrief() {
    const url = briefDate
      ? `/api/briefs/trigger?week_ending=${briefDate}`
      : "/api/briefs/trigger";
    await api.post(url, {});
    setBriefMsg(`Brief generation triggered${briefDate ? ` for ${briefDate}` : ""} — check back in ~30s.`);
    setTimeout(() => setBriefMsg(null), 8000);
  }

  async function resolve(id: number, isGolden: boolean) {
    await api.patch(`/api/admin/review-queue/${id}?is_golden=${isGolden}`, {});
    qc.invalidateQueries({ queryKey: ["review-queue"] });
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", background: "var(--bg-page)" }}>
      <main style={{ maxWidth: "1100px", margin: "0 auto", padding: "32px 32px 80px" }}>

        {/* ── LLM Budget ── */}
        {budget && (
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            padding: "16px 20px",
            marginBottom: "24px",
          }}>
            <div style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "12px",
            }}>
              <span style={{
                fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
                textTransform: "uppercase", color: "var(--text-tertiary)",
              }}>
                LLM Budget
              </span>
              <div style={{ display: "flex", gap: "20px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px" }}>
                {[
                  { label: "today", value: `$${budget.today_usd.toFixed(4)}` },
                  { label: "yesterday", value: `$${budget.yesterday_usd.toFixed(4)}` },
                  { label: "7-day", value: `$${budget.week_usd.toFixed(2)}` },
                  { label: "cap", value: `$${budget.daily_cap_usd}` },
                  { label: "used", value: `${budget.budget_pct.toFixed(1)}%` },
                ].map(({ label, value }) => (
                  <span key={label} style={{ color: "var(--text-tertiary)" }}>
                    <span style={{ color: "var(--text-secondary)" }}>{value}</span>
                    {" "}{label}
                  </span>
                ))}
              </div>
            </div>
            {budgetHistory && budgetHistory.length > 0 && (
              <BudgetSparkline data={budgetHistory} dailyCap={budget.daily_cap_usd} />
            )}
          </div>
        )}

        {/* ── Recent LLM Calls ── */}
        {llmCalls && llmCalls.length > 0 && (
          <div style={{ marginBottom: "24px" }}>
            <div style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "8px",
            }}>
              <span style={{
                fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
                textTransform: "uppercase", color: "var(--text-tertiary)",
              }}>
                Recent LLM Calls
              </span>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)" }}>
                last {llmCalls.length} · ${llmCalls.reduce((s, r) => s + r.cost_usd, 0).toFixed(4)} total
              </span>
            </div>
            <div style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              overflow: "hidden",
              maxHeight: "280px",
              overflowY: "auto",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead style={{ position: "sticky", top: 0, background: "var(--bg-surface)", zIndex: 1 }}>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Time", "Model", "Task", "In", "Out", "Cache↑", "Cache↓", "Cost", ""].map(h => (
                      <th key={h} style={{
                        padding: "6px 10px",
                        textAlign: "left",
                        fontSize: "8px",
                        fontWeight: 700,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        color: "var(--text-tertiary)",
                        whiteSpace: "nowrap",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {llmCalls.map((call, i) => (
                    <LLMCallRow key={call.id} call={call} isLast={i === llmCalls.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Budget by Task ── */}
        {budgetByTask && budgetByTask.length > 0 && (
          <div style={{ marginBottom: "24px" }}>
            <div style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "8px",
            }}>
              <span style={{
                fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
                textTransform: "uppercase", color: "var(--text-tertiary)",
              }}>
                Budget by Task — Last 7 Days
              </span>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)" }}>
                ${budgetByTask.reduce((s, r) => s + r.spend_usd, 0).toFixed(4)} total
              </span>
            </div>
            <div style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Task", "Calls", "In Tokens", "Out Tokens", "Cache Read", "Cache Ratio", "Cost"].map(h => (
                      <th key={h} style={{
                        padding: "6px 10px",
                        textAlign: "left",
                        fontSize: "8px",
                        fontWeight: 700,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        color: "var(--text-tertiary)",
                        whiteSpace: "nowrap",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {budgetByTask.map((row, i) => (
                    <TaskBreakdownRow key={row.task_type} row={row} isLast={i === budgetByTask.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Quick actions bar ── */}
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          padding: "12px 20px",
          marginBottom: "24px",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          flexWrap: "wrap",
        }}>
          <span style={{
            fontSize: "9px", fontWeight: 700, letterSpacing: "0.16em",
            textTransform: "uppercase", color: "var(--text-tertiary)",
            flexShrink: 0,
          }}>
            Pipeline
          </span>
          {[
            { label: "Fetch Bodies", step: "news_body" },
            { label: "Extract Facts", step: "news_extract" },
          ].map(({ label, step }) => (
            <button
              key={step}
              onClick={async () => {
                await api.post(`/api/admin/pipeline/${step}/trigger`, {});
                setBriefMsg(`${label} triggered — processing in background.`);
                setTimeout(() => setBriefMsg(null), 6000);
              }}
              style={navBtnStyle}
            >
              {label}
            </button>
          ))}
          <div style={{ width: "1px", height: "14px", background: "var(--border)" }} />
          <span style={{
            fontSize: "9px", fontWeight: 700, letterSpacing: "0.16em",
            textTransform: "uppercase", color: "var(--text-tertiary)",
            flexShrink: 0,
          }}>
            Brief
          </span>
          <input
            type="date"
            value={briefDate}
            onChange={e => setBriefDate(e.target.value)}
            style={{
              background: "var(--bg-page)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "10px",
              padding: "3px 8px",
              outline: "none",
            }}
          />
          <button onClick={triggerBrief} style={navBtnStyle}>
            Generate
          </button>
          {briefMsg && (
            <span style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "10px",
              color: "var(--brand-navy)",
            }}>
              {briefMsg}
            </span>
          )}
        </div>

        <div style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: "24px",
        }}>
          <div>
            <h2 style={{
              fontFamily: "var(--font-display)",
              fontSize: "26px",
              fontWeight: 400,
              fontStyle: "italic",
              color: "var(--text-primary)",
              margin: "0 0 4px",
            }}>
              Review Queue
            </h2>
            <p style={{
              fontSize: "11px",
              color: "var(--text-tertiary)",
              margin: 0,
              fontFamily: "'IBM Plex Mono', monospace",
            }}>
              LLM extractions with confidence ≤ 3 — approve, reject, or add to golden set
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "10px", color: "var(--text-tertiary)" }}>
              Pending only
            </span>
            <button
              onClick={() => setPendingOnly(v => !v)}
              style={{
                ...navBtnStyle,
                color: pendingOnly ? "var(--brand-navy)" : "var(--text-tertiary)",
                borderColor: pendingOnly ? "var(--brand-navy)" : "var(--border)",
              }}
            >
              {pendingOnly ? "ON" : "OFF"}
            </button>
          </div>
        </div>

        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{
                height: "120px",
                background: "var(--bg-surface)",
                opacity: 0.3,
              }} />
            ))}
          </div>
        )}

        {!isLoading && (!items || items.length === 0) && (
          <div style={{
            padding: "48px",
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            textAlign: "center",
          }}>
            <p style={{
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: "18px",
              color: "var(--text-secondary)",
              margin: "0 0 8px",
            }}>
              Queue is clear.
            </p>
            <p style={{
              fontSize: "11px",
              color: "var(--text-tertiary)",
              fontFamily: "'IBM Plex Mono', monospace",
              margin: 0,
            }}>
              All extractions are high-confidence or already reviewed.
            </p>
          </div>
        )}

        {items && items.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{
              fontSize: "10px",
              color: "var(--text-tertiary)",
              fontFamily: "'IBM Plex Mono', monospace",
              marginBottom: "4px",
            }}>
              {items.length} item{items.length !== 1 ? "s" : ""}
            </div>
            {items.map(item => (
              <ReviewCard
                key={item.id}
                item={item}
                onApprove={() => resolve(item.id, false)}
                onGolden={() => resolve(item.id, true)}
                onReject={() => resolve(item.id, false)}
              />
            ))}
          </div>
        )}
        {/* ── Jobs / Source Registry ── */}
        {jobs && jobs.length > 0 && (
          <div style={{ marginTop: "48px" }}>
            <div style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "12px",
            }}>
              <h2 style={{
                fontFamily: "var(--font-display)",
                fontSize: "20px",
                fontWeight: 400,
                fontStyle: "italic",
                color: "var(--text-primary)",
                margin: 0,
              }}>
                Data Sources
              </h2>
              <span style={{ fontSize: "10px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace" }}>
                {jobs.filter(j => j.stale).length} stale
              </span>
            </div>
            <div style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Source", "Type", "Last Success", "Age", "Failures", "Status", ""].map(h => (
                      <th key={h} style={{
                        padding: "8px 14px",
                        textAlign: "left",
                        fontSize: "8px",
                        fontWeight: 700,
                        letterSpacing: "0.14em",
                        textTransform: "uppercase",
                        color: "var(--text-tertiary)",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job, i) => (
                    <JobRow
                      key={job.source_key}
                      job={job}
                      isLast={i === jobs.length - 1}
                      onTrigger={async () => {
                        await api.post(`/api/admin/scraper/${job.source_key}/trigger`, {});
                        qc.invalidateQueries({ queryKey: ["admin-jobs"] });
                      }}
                      onToggle={async () => {
                        await api.patch(`/api/admin/sources/${job.source_key}?enabled=${!job.is_enabled}`, {});
                        qc.invalidateQueries({ queryKey: ["admin-jobs"] });
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Scheduler ── */}
        {schedule && schedule.length > 0 && (
          <div style={{ marginTop: "48px" }}>
            <div style={{
              fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
              textTransform: "uppercase", color: "var(--text-tertiary)",
              marginBottom: "12px",
              paddingBottom: "8px",
              borderBottom: "1px solid var(--border)",
            }}>
              Scheduler — Next Fire Times
            </div>
            <div style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Job", "Next Run", "In"].map(h => (
                      <th key={h} style={{
                        padding: "7px 14px",
                        textAlign: "left",
                        fontSize: "8px",
                        fontWeight: 700,
                        letterSpacing: "0.14em",
                        textTransform: "uppercase",
                        color: "var(--text-tertiary)",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {schedule.map((entry, i) => (
                    <ScheduleRow key={entry.id} entry={entry} isLast={i === schedule.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Circuit Breakers ── */}
        {breakers && breakers.length > 0 && (
          <div style={{ marginTop: "48px" }}>
            <div style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "12px",
              paddingBottom: "8px",
              borderBottom: "1px solid var(--border)",
            }}>
              <div style={{
                fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
                textTransform: "uppercase", color: "var(--text-tertiary)",
              }}>
                Circuit Breakers
              </div>
              <span style={{ fontSize: "10px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace" }}>
                {breakers.filter(b => b.state !== "closed").length} open
              </span>
            </div>
            <div style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Source", "State", "Failures", "Max", "Reset"].map(h => (
                      <th key={h} style={{
                        padding: "7px 14px",
                        textAlign: "left",
                        fontSize: "8px",
                        fontWeight: 700,
                        letterSpacing: "0.14em",
                        textTransform: "uppercase",
                        color: "var(--text-tertiary)",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {breakers.map((b, i) => (
                    <BreakerRow key={b.name} breaker={b} isLast={i === breakers.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Failed Outbox ── */}
        {failedOutbox && failedOutbox.length > 0 && (
          <div style={{ marginTop: "48px" }}>
            <div style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "12px",
              paddingBottom: "8px",
              borderBottom: "1px solid rgba(248,113,113,0.3)",
            }}>
              <div style={{
                fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
                textTransform: "uppercase", color: "#f87171",
              }}>
                Failed Extractions
              </div>
              <span style={{ fontSize: "10px", color: "#fca5a5", fontFamily: "'IBM Plex Mono', monospace" }}>
                {failedOutbox.length} row{failedOutbox.length !== 1 ? "s" : ""} permanently failed
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              {failedOutbox.map(row => (
                <FailedOutboxCard key={row.id} row={row} />
              ))}
            </div>
          </div>
        )}

        {/* ── District Registry ── */}
        <div style={{ marginTop: "48px" }}>
          <div style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: "12px",
            paddingBottom: "8px",
            borderBottom: "1px solid var(--border)",
          }}>
            <div style={{
              fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
              textTransform: "uppercase", color: "var(--text-tertiary)",
            }}>
              District Registry
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="text"
                value={districtCity}
                onChange={e => setDistrictCity(e.target.value)}
                placeholder="filter by city…"
                style={{
                  background: "var(--bg-page)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "10px",
                  padding: "2px 8px",
                  outline: "none",
                  width: "160px",
                }}
              />
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)" }}>
                {districts?.length ?? 0} canonical
              </span>
            </div>
          </div>

          {/* Add alias form */}
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            padding: "12px 16px",
            marginBottom: "12px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            flexWrap: "wrap",
          }}>
            <span style={{
              fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em",
              textTransform: "uppercase", color: "var(--text-tertiary)",
              flexShrink: 0,
            }}>
              Add Alias
            </span>
            <select
              value={newAliasDistrictId ?? ""}
              onChange={e => setNewAliasDistrictId(e.target.value ? Number(e.target.value) : null)}
              style={{
                background: "var(--bg-page)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "10px",
                padding: "2px 6px",
                outline: "none",
                maxWidth: "200px",
              }}
            >
              <option value="">— select district —</option>
              {districts?.map(d => (
                <option key={d.canonical_id} value={d.canonical_id}>
                  [{d.city}] {d.name_en ?? d.name_ar ?? `#${d.canonical_id}`}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={newAlias}
              onChange={e => setNewAlias(e.target.value)}
              placeholder="alias text"
              style={{
                background: "var(--bg-page)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "10px",
                padding: "2px 8px",
                outline: "none",
                width: "180px",
              }}
            />
            <select
              value={newAliasLang}
              onChange={e => setNewAliasLang(e.target.value)}
              style={{
                background: "var(--bg-page)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "10px",
                padding: "2px 6px",
                outline: "none",
              }}
            >
              {["en", "ar"].map(l => <option key={l} value={l}>{l}</option>)}
            </select>
            <button
              onClick={addAlias}
              disabled={!newAliasDistrictId || !newAlias.trim()}
              style={{
                ...navBtnStyle,
                opacity: (!newAliasDistrictId || !newAlias.trim()) ? 0.4 : 1,
              }}
            >
              Add
            </button>
            {aliasMsg && (
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--brand-navy)" }}>
                {aliasMsg}
              </span>
            )}
          </div>

          {/* District list */}
          {districts && districts.length > 0 && (
            <div style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              overflow: "hidden",
              maxHeight: "320px",
              overflowY: "auto",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead style={{ position: "sticky", top: 0, background: "var(--bg-surface)", zIndex: 1 }}>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["ID", "City", "English", "Arabic", "Aliases"].map(h => (
                      <th key={h} style={{
                        padding: "6px 12px",
                        textAlign: "left",
                        fontSize: "8px",
                        fontWeight: 700,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        color: "var(--text-tertiary)",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {districts.map((d, i) => (
                    <DistrictRow key={d.canonical_id} district={d} isLast={i === districts.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Rent Index CSV Import ── */}
        <div style={{ marginTop: "48px" }}>
          <div style={{
            fontSize: "9px", fontWeight: 700, letterSpacing: "0.18em",
            textTransform: "uppercase", color: "var(--text-tertiary)",
            marginBottom: "12px",
            paddingBottom: "8px",
            borderBottom: "1px solid var(--border)",
          }}>
            Rent Index — Import CSV
          </div>
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            flexWrap: "wrap",
          }}>
            <span style={{ fontSize: "10px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace" }}>
              Required columns: <code style={{ color: "var(--brand-navy)" }}>district, property_type, period, rent_sar_sqm_annual</code>
            </span>
            <input
              type="text"
              value={importSource}
              onChange={e => setImportSource(e.target.value)}
              placeholder="source name"
              style={{
                background: "var(--bg-page)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "10px",
                padding: "3px 8px",
                outline: "none",
                width: "160px",
              }}
            />
            <input
              type="file"
              accept=".csv"
              style={{ fontSize: "10px", color: "var(--text-secondary)", fontFamily: "'IBM Plex Mono', monospace" }}
              onChange={async e => {
                const file = e.target.files?.[0];
                if (!file) return;
                const form = new FormData();
                form.append("file", file);
                const url = `/api/admin/rent-index/import?source=${encodeURIComponent(importSource)}`;
                const resp = await fetch(url, {
                  method: "POST",
                  headers: { Authorization: `Bearer ${localStorage.getItem("ws_token")}` },
                  body: form,
                });
                const data = await resp.json();
                if (resp.ok) {
                  setImportMsg(`Imported ${data.inserted} rows, skipped ${data.skipped}.`);
                  qc.invalidateQueries({ queryKey: ["rent-index"] });
                } else {
                  setImportMsg(`Error: ${data.detail ?? "upload failed"}`);
                }
                setTimeout(() => setImportMsg(null), 8000);
                e.target.value = "";
              }}
            />
            {importMsg && (
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--brand-navy)" }}>
                {importMsg}
              </span>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function ScheduleRow({ entry, isLast }: { entry: ScheduleEntry; isLast: boolean }) {
  const nextLabel = entry.next_fire_time
    ? new Date(entry.next_fire_time).toLocaleString("en-GB", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : "—";

  const inLabel = entry.minutes_until != null
    ? entry.minutes_until < 60
      ? `${Math.round(entry.minutes_until)}m`
      : `${(entry.minutes_until / 60).toFixed(1)}h`
    : "—";

  const urgent = entry.minutes_until != null && entry.minutes_until < 10;

  return (
    <tr style={{ borderBottom: isLast ? "none" : "1px solid var(--border)" }}>
      <td style={{
        padding: "9px 14px",
        fontSize: "11px",
        fontFamily: "'IBM Plex Mono', monospace",
        color: "var(--text-primary)",
      }}>
        {entry.id}
      </td>
      <td style={{
        padding: "9px 14px",
        fontSize: "11px",
        fontFamily: "'IBM Plex Mono', monospace",
        color: "var(--text-secondary)",
        fontVariantNumeric: "tabular-nums",
      }}>
        {nextLabel}
      </td>
      <td style={{
        padding: "9px 14px",
        fontSize: "11px",
        fontFamily: "'IBM Plex Mono', monospace",
        color: urgent ? "var(--brand-navy)" : "var(--text-tertiary)",
        fontVariantNumeric: "tabular-nums",
      }}>
        {inLabel}
      </td>
    </tr>
  );
}

function JobRow({ job, isLast, onTrigger, onToggle }: { job: JobStatus; isLast: boolean; onTrigger: () => void; onToggle: () => void }) {
  const statusColor = !job.is_enabled
    ? "var(--text-tertiary)"
    : job.stale
      ? "#f87171"
      : job.consecutive_failures > 0
        ? "#fb923c"
        : "#4ade80";

  const statusLabel = !job.is_enabled
    ? "disabled"
    : job.stale
      ? "stale"
      : job.consecutive_failures > 0
        ? `${job.consecutive_failures} fail${job.consecutive_failures !== 1 ? "s" : ""}`
        : "ok";

  return (
    <tr style={{
      borderBottom: isLast ? "none" : "1px solid var(--border)",
    }}>
      <td style={{ padding: "10px 14px", fontSize: "12px", color: "var(--text-primary)" }}>
        {job.display_name}
        <div style={{ fontSize: "9px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace", marginTop: "2px" }}>
          {job.source_key}
        </div>
      </td>
      <td style={{ padding: "10px 14px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "9px",
          color: "var(--text-tertiary)",
          border: "1px solid var(--border)",
          padding: "1px 5px",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}>
          {job.source_type}
        </span>
      </td>
      <td style={{ padding: "10px 14px", fontSize: "11px", color: "var(--text-secondary)", fontFamily: "'IBM Plex Mono', monospace", fontVariantNumeric: "tabular-nums" }}>
        {job.last_success_at ? formatDate(job.last_success_at) : <span style={{ color: "var(--text-tertiary)" }}>never</span>}
      </td>
      <td style={{ padding: "10px 14px", fontSize: "11px", fontFamily: "'IBM Plex Mono', monospace", fontVariantNumeric: "tabular-nums", color: job.stale ? "#f87171" : "var(--text-tertiary)" }}>
        {job.age_hours != null ? `${job.age_hours}h` : "—"}
      </td>
      <td style={{ padding: "10px 14px", fontSize: "11px", fontVariantNumeric: "tabular-nums", color: job.consecutive_failures > 0 ? "#fb923c" : "var(--text-tertiary)" }}>
        {job.consecutive_failures}
      </td>
      <td style={{ padding: "10px 14px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "9px",
          fontWeight: 700,
          color: statusColor,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}>
          {statusLabel}
        </span>
      </td>
      <td style={{ padding: "10px 14px" }}>
        <div style={{ display: "flex", gap: "4px" }}>
          <button
            onClick={onTrigger}
            style={{
              background: "transparent",
              border: "1px solid var(--border)",
              color: "var(--text-tertiary)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "8px",
              letterSpacing: "0.1em",
              padding: "2px 7px",
              cursor: "pointer",
              textTransform: "uppercase",
            }}
          >
            Run
          </button>
          <button
            onClick={onToggle}
            style={{
              background: "transparent",
              border: `1px solid ${job.is_enabled ? "var(--border)" : "rgba(201,146,42,0.4)"}`,
              color: job.is_enabled ? "var(--text-tertiary)" : "var(--brand-navy)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "8px",
              letterSpacing: "0.1em",
              padding: "2px 7px",
              cursor: "pointer",
              textTransform: "uppercase",
            }}
          >
            {job.is_enabled ? "Disable" : "Enable"}
          </button>
        </div>
      </td>
    </tr>
  );
}

function ReviewCard({
  item, onApprove, onGolden, onReject,
}: {
  item: ReviewItem;
  onApprove: () => void;
  onGolden: () => void;
  onReject: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const confidenceColor =
    item.confidence == null ? "var(--text-tertiary)"
    : item.confidence <= 2   ? "#f87171"
    : item.confidence === 3  ? "#fb923c"
    : "var(--text-tertiary)";

  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderLeft: `2px solid ${confidenceColor}`,
    }}>
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "16px",
          padding: "14px 16px",
          cursor: "pointer",
        }}
        onClick={() => setExpanded(v => !v)}
        onMouseEnter={e => {
          (e.currentTarget as HTMLDivElement).style.background = "var(--bg-hover)";
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLDivElement).style.background = "transparent";
        }}
      >
        {/* Confidence badge */}
        <div style={{
          flexShrink: 0,
          width: "28px",
          textAlign: "right",
          paddingTop: "1px",
        }}>
          <span style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "13px",
            fontWeight: 700,
            color: confidenceColor,
          }}>
            {item.confidence ?? "?"}
          </span>
          <div style={{ fontSize: "8px", color: "var(--text-tertiary)", marginTop: "1px" }}>
            /5
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px" }}>
            <span className="source-badge">{item.source_table}</span>
            <span style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "10px",
              color: "var(--text-tertiary)",
            }}>
              row #{item.source_row_id}
            </span>
            {item.model_id && (
              <span style={{
                fontSize: "9px",
                color: "var(--text-tertiary)",
                fontFamily: "'IBM Plex Mono', monospace",
              }}>
                {item.model_id.replace("claude-", "")}
              </span>
            )}
            {item.is_golden && (
              <span style={{
                fontSize: "8px",
                fontWeight: 700,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--brand-navy)",
                border: "1px solid var(--brand-navy)",
                padding: "0 4px",
              }}>
                golden
              </span>
            )}
          </div>

          {item.uncertain_fields.length > 0 && (
            <div style={{ marginBottom: "5px" }}>
              <span style={{
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                marginRight: "6px",
              }}>
                Uncertain:
              </span>
              {item.uncertain_fields.map(f => (
                <span key={f} style={{
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "10px",
                  color: "#fb923c",
                  marginRight: "8px",
                }}>
                  {f}
                </span>
              ))}
            </div>
          )}

          <div style={{ fontSize: "10px", color: "var(--text-tertiary)" }}>
            {formatDate(item.created_at)}
          </div>
        </div>

        <div style={{
          flexShrink: 0,
          color: "var(--text-tertiary)",
          fontSize: "11px",
        }}>
          {expanded ? "▲" : "▼"}
        </div>
      </div>

      {/* Expanded output */}
      {expanded && (
        <div style={{ borderTop: "1px solid var(--border)" }}>
          <pre style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "10px",
            color: "var(--text-secondary)",
            whiteSpace: "pre-wrap",
            lineHeight: 1.65,
            margin: 0,
            padding: "16px",
            background: "var(--bg-page)",
            maxHeight: "300px",
            overflowY: "auto",
          }}>
            {JSON.stringify(item.llm_output, null, 2)}
          </pre>

          {/* Action buttons */}
          <div style={{
            display: "flex",
            gap: "8px",
            padding: "12px 16px",
            borderTop: "1px solid var(--border)",
            background: "var(--bg-surface)",
          }}>
            <ActionButton
              label="Approve"
              color="var(--text-tertiary)"
              onClick={e => { e.stopPropagation(); onApprove(); }}
            />
            <ActionButton
              label="Add to Golden Set"
              color="var(--brand-navy)"
              onClick={e => { e.stopPropagation(); onGolden(); }}
            />
            <ActionButton
              label="Reject"
              color="#f87171"
              onClick={e => { e.stopPropagation(); onReject(); }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function ActionButton({
  label, color, onClick,
}: {
  label: string;
  color: string;
  onClick: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: "transparent",
        border: `1px solid ${color}`,
        color,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "9px",
        letterSpacing: "0.1em",
        padding: "4px 10px",
        cursor: "pointer",
        textTransform: "uppercase",
        transition: "background 120ms ease",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLButtonElement).style.background =
          color.replace("var(", "").replace(")", "") === color
            ? color + "22"
            : "var(--bg-hover)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLButtonElement).style.background = "transparent";
      }}
    >
      {label}
    </button>
  );
}

function LLMCallRow({ call, isLast }: { call: LLMCallRow; isLast: boolean }) {
  const timeLabel = new Date(call.called_at).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const dateLabel = new Date(call.called_at).toLocaleDateString("en-GB", {
    day: "numeric", month: "short",
  });
  const cacheHitPct = call.input_tokens > 0
    ? Math.round((call.cache_read_tokens / (call.input_tokens + call.cache_read_tokens)) * 100)
    : 0;

  return (
    <tr style={{ borderBottom: isLast ? "none" : "1px solid var(--border)" }}>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "var(--text-tertiary)", whiteSpace: "nowrap" }}>
        <div>{dateLabel}</div>
        <div>{timeLabel}</div>
      </td>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
        {call.model_id.replace("claude-", "").replace("-20251001", "")}
      </td>
      <td style={{ padding: "6px 10px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: "8px", letterSpacing: "0.08em",
          textTransform: "uppercase", color: "var(--text-tertiary)",
          border: "1px solid var(--border)", padding: "1px 4px",
        }}>
          {call.task_type}
        </span>
      </td>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {call.input_tokens.toLocaleString()}
      </td>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {call.output_tokens.toLocaleString()}
      </td>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: call.cache_write_tokens > 0 ? "var(--brand-navy)" : "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {call.cache_write_tokens > 0 ? call.cache_write_tokens.toLocaleString() : "—"}
      </td>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: call.cache_read_tokens > 0 ? "#4ade80" : "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {call.cache_read_tokens > 0 ? `${call.cache_read_tokens.toLocaleString()} (${cacheHitPct}%)` : "—"}
      </td>
      <td style={{ padding: "6px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "var(--brand-navy)", fontVariantNumeric: "tabular-nums" }}>
        ${call.cost_usd.toFixed(4)}
      </td>
      <td style={{ padding: "6px 10px" }}>
        {!call.success && (
          <span style={{ fontSize: "8px", color: "#f87171", fontFamily: "'IBM Plex Mono', monospace", textTransform: "uppercase" }}>fail</span>
        )}
        {call.is_batch && (
          <span style={{ fontSize: "8px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace", textTransform: "uppercase" }}>batch</span>
        )}
      </td>
    </tr>
  );
}

function FailedOutboxCard({ row }: { row: FailedOutboxRow }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid rgba(248,113,113,0.2)",
      borderLeft: "2px solid #f87171",
    }}>
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          padding: "10px 14px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
          cursor: "pointer",
        }}
      >
        <span className="source-badge">{row.source}</span>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "10px",
          color: "var(--text-secondary)",
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}>
          {row.extraction_error ?? "(no error message)"}
        </span>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "9px",
          color: "var(--text-tertiary)",
          flexShrink: 0,
        }}>
          {formatDate(row.fetched_at)}
        </span>
        <span style={{ color: "var(--text-tertiary)", fontSize: "10px", flexShrink: 0 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>
      {expanded && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "10px 14px" }}>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "var(--text-tertiary)", marginBottom: "6px" }}>
            URI: <span style={{ color: "var(--text-secondary)" }}>{row.raw_uri}</span>
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", color: "#f87171" }}>
            {row.extraction_error ?? "(no error recorded)"}
          </div>
        </div>
      )}
    </div>
  );
}

function BreakerRow({ breaker, isLast }: { breaker: CircuitBreakerStatus; isLast: boolean }) {
  const stateColor =
    breaker.state === "open"
      ? "#f87171"
      : breaker.state === "half-open"
        ? "#fb923c"
        : "#4ade80";

  return (
    <tr style={{ borderBottom: isLast ? "none" : "1px solid var(--border)" }}>
      <td style={{ padding: "9px 14px", fontSize: "12px", color: "var(--text-primary)", fontFamily: "'IBM Plex Mono', monospace" }}>
        {breaker.name}
      </td>
      <td style={{ padding: "9px 14px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "9px",
          fontWeight: 700,
          color: stateColor,
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}>
          {breaker.state}
        </span>
      </td>
      <td style={{ padding: "9px 14px", fontSize: "11px", fontVariantNumeric: "tabular-nums", color: breaker.fail_counter > 0 ? "#fb923c" : "var(--text-tertiary)" }}>
        {breaker.fail_counter}
      </td>
      <td style={{ padding: "9px 14px", fontSize: "11px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {breaker.fail_max}
      </td>
      <td style={{ padding: "9px 14px", fontSize: "11px", color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace" }}>
        {breaker.reset_timeout_s}s
      </td>
    </tr>
  );
}

function TaskBreakdownRow({ row, isLast }: { row: TaskBreakdown; isLast: boolean }) {
  const totalIn = row.input_tokens + row.cache_read_tokens;
  const cacheRatio = totalIn > 0
    ? Math.round((row.cache_read_tokens / totalIn) * 100)
    : 0;

  return (
    <tr style={{ borderBottom: isLast ? "none" : "1px solid var(--border)" }}>
      <td style={{ padding: "7px 10px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: "8px", letterSpacing: "0.08em",
          textTransform: "uppercase", color: "var(--text-secondary)",
          border: "1px solid var(--border)", padding: "1px 5px",
        }}>
          {row.task_type}
        </span>
      </td>
      <td style={{ padding: "7px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {row.calls.toLocaleString()}
      </td>
      <td style={{ padding: "7px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {row.input_tokens.toLocaleString()}
      </td>
      <td style={{ padding: "7px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {row.output_tokens.toLocaleString()}
      </td>
      <td style={{ padding: "7px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: row.cache_read_tokens > 0 ? "#4ade80" : "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {row.cache_read_tokens > 0 ? row.cache_read_tokens.toLocaleString() : "—"}
      </td>
      <td style={{ padding: "7px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", fontVariantNumeric: "tabular-nums", color: cacheRatio > 50 ? "#4ade80" : "var(--text-tertiary)" }}>
        {cacheRatio > 0 ? `${cacheRatio}%` : "—"}
      </td>
      <td style={{ padding: "7px 10px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--brand-navy)", fontVariantNumeric: "tabular-nums" }}>
        ${row.spend_usd.toFixed(4)}
      </td>
    </tr>
  );
}

function DistrictRow({ district, isLast }: { district: DistrictGroup; isLast: boolean }) {
  return (
    <tr style={{ borderBottom: isLast ? "none" : "1px solid var(--border)" }}>
      <td style={{ padding: "7px 12px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "var(--text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
        {district.canonical_id}
      </td>
      <td style={{ padding: "7px 12px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px", textTransform: "uppercase",
          letterSpacing: "0.08em", color: "var(--text-tertiary)",
          border: "1px solid var(--border)", padding: "1px 5px",
        }}>
          {district.city}
        </span>
      </td>
      <td style={{ padding: "7px 12px", fontSize: "11px", color: "var(--text-primary)" }}>
        {district.name_en ?? <span style={{ color: "var(--text-tertiary)" }}>—</span>}
      </td>
      <td style={{ padding: "7px 12px", fontSize: "11px", color: "var(--text-secondary)", direction: "rtl" }}>
        {district.name_ar ?? <span style={{ color: "var(--text-tertiary)", direction: "ltr" }}>—</span>}
      </td>
      <td style={{ padding: "7px 12px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
          {district.aliases.map((a, i) => (
            <span key={i} style={{
              fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px",
              color: a.lang === "ar" ? "var(--text-secondary)" : "var(--text-tertiary)",
              border: "1px solid var(--border)", padding: "1px 5px",
            }}>
              {a.alias}
              <span style={{ color: "var(--text-tertiary)", marginLeft: "3px" }}>{a.lang}</span>
            </span>
          ))}
          {district.aliases.length === 0 && (
            <span style={{ color: "var(--text-tertiary)", fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px" }}>none</span>
          )}
        </div>
      </td>
    </tr>
  );
}

const navBtnStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--border)",
  color: "var(--text-tertiary)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "9px",
  letterSpacing: "0.1em",
  padding: "3px 8px",
  cursor: "pointer",
  textTransform: "uppercase",
};
