// Admin — review queue, sources, users, LLM budget

import { useState } from "react";

const reviewQueue = [
  { id: "#4821", t: "transaction", title: "Allianz acquires Generation Park Y for €119m at 5.85% yield",       src: "Eurobuild CEE",          ingested: "06:08",     conf: 5, status: "pending" },
  { id: "#4820", t: "sentiment",   title: "FINN bill amendments — distribution mandate raised to 90%",          src: "Rzeczpospolita · NRC",   ingested: "05:14",     conf: 4, status: "pending" },
  { id: "#4819", t: "transaction", title: "Marvipol repriced 6 units in Unisono Wola (+2.23%)",                 src: "MRiT · Jawność feed",   ingested: "02:12",     conf: 5, status: "auto"    },
  { id: "#4818", t: "sentiment",   title: "WSA Warsaw upholds 'Czyste-Towarowa' MPZP — 130m height ceiling",   src: "Eurobuild CEE",          ingested: "yesterday", conf: 5, status: "pending" },
  { id: "#4817", t: "listing",     title: "Skanska Property lists Studio B floors 8–12 at €25.50/sqm/mo",      src: "Property Forum",         ingested: "05:42",     conf: 5, status: "pending" },
  { id: "#4816", t: "transaction", title: "Echo Browary Warszawskie etap VI — 14 units repriced +1.64%",       src: "Jawność feed",           ingested: "03:55",     conf: 4, status: "flagged" },
  { id: "#4815", t: "sentiment",   title: "Citi BPO renews V.Offices + 3,000 sqm expansion",                   src: "Property Forum",         ingested: "04:18",     conf: 5, status: "pending" },
  { id: "#4814", t: "transaction", title: "PFA-Norway · €286m write at Forest Tower (5.50%)",                  src: "Bankier",                ingested: "05:28",     conf: 5, status: "pending" },
];

const sourceRegistry = [
  { n: "Eurobuild CEE",  type: "Trade press",  status: "healthy", lastIngest: "06:08",     facts7d: 142, errors: 0, note: "" },
  { n: "Property Forum", type: "Trade press",  status: "healthy", lastIngest: "05:42",     facts7d:  98, errors: 0, note: "" },
  { n: "MRiT · Jawność", type: "Government",   status: "healthy", lastIngest: "06:14",     facts7d: 412, errors: 0, note: "" },
  { n: "GUGiK · RCN",   type: "Government",   status: "healthy", lastIngest: "04:22",     facts7d: 142, errors: 0, note: "Rejestr Cen Nieruchomości · land transactions" },
  { n: "Bankier",        type: "Mainstream",   status: "healthy", lastIngest: "05:28",     facts7d:  64, errors: 0, note: "" },
  { n: "Sejm RP · druk", type: "Government",   status: "healthy", lastIngest: "yesterday", facts7d:  14, errors: 0, note: "" },
  { n: "GUS BDL",        type: "Government",   status: "healthy", lastIngest: "yesterday", facts7d:  32, errors: 0, note: "" },
  { n: "NBP",            type: "Government",   status: "healthy", lastIngest: "02:00",     facts7d:  28, errors: 0, note: "" },
];

const users = [
  { n: "Karol Wiśniewski",   role: "Admin",  org: "WSRE",                last: "now",       seats: 1 },
  { n: "Anna Kowalska",      role: "Editor", org: "WSRE",                last: "03:42",     seats: 1 },
  { n: "James Whitfield",    role: "Reader", org: "PFA-Norway",          last: "yesterday", seats: 6 },
  { n: "Hans Brückner",      role: "Reader", org: "Allianz Real Estate", last: "08 Apr",    seats: 8 },
  { n: "Tomasz Lewandowski", role: "Reader", org: "Echo Investment",     last: "11 Apr",    seats: 4 },
  { n: "Margarethe Lin",     role: "Reader", org: "Family Office (CH)",  last: "02 Apr",    seats: 2 },
];

const budgetRows: [string, number, number, number][] = [
  ["Fact extraction",         8420,  4280, 412],
  ["Brief synthesis",          168,   620, 184],
  ["Plot report generation",    62,   880, 264],
  ["Translation (PL→EN)",     2440,   320,  96],
  ["MPZP text parsing",         48,   210,  64],
  ["Confidence scoring",      9220,   180,  42],
  ["Source classification",   8420,   140,  32],
  ["Other",                    140,   860, 746],
];

const macroOverrides: [string, string, string][] = [
  ["NBP Reference Rate", "5.25 %", "02 Apr 2026"],
  ["EUR / PLN",          "4.2840", "13 Apr 2026"],
  ["Polish 10Y",         "5.18 %", "13 Apr 2026"],
  ["CPI YoY",            "4.6 %",  "Mar 2026"],
  ["Unemployment",       "5.1 %",  "Mar 2026"],
];

function initials(name: string) {
  return name.split(" ").map(p => p[0]).join("").slice(0, 3);
}

export function AdminPage() {
  const [tab, setTab] = useState("queue");

  const tabs: [string, string][] = [
    ["queue",   "Review queue (8)"],
    ["sources", "Sources (16)"],
    ["users",   "Users & seats"],
    ["budget",  "LLM budget"],
  ];

  return (
    <div style={{ padding: "32px 48px 48px", maxWidth: 1500, margin: "0 auto", overflowY: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <h1 className="ws-page-title">Admin</h1>
        <div className="tnum" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          14 Apr 2026 · LLM budget €1,840 / €4,000 month
        </div>
      </div>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 24 }}>
        Internal operations — fact review, source registry, user management.
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border)", marginBottom: 24 }}>
        {tabs.map(([k, l]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            style={{
              padding: "10px 18px", border: "none", background: "transparent",
              borderBottom: tab === k ? "2px solid var(--brand-navy)" : "2px solid transparent",
              color: tab === k ? "var(--text-primary)" : "var(--text-secondary)",
              fontFamily: "inherit", fontSize: 13, cursor: "pointer",
              fontWeight: tab === k ? 500 : 400,
            }}
          >
            {l}
          </button>
        ))}
      </div>

      {/* Review queue */}
      {tab === "queue" && (
        <div className="ws-card" style={{ padding: 0 }}>
          <div style={{ padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--divider)" }}>
            <div style={{ display: "flex", gap: 8 }}>
              {["All (8)", "Pending (6)", "Flagged (1)", "Auto-approved (1)"].map((l, i) => (
                <span key={i} className={"chip" + (i === 0 ? " active" : "")}>{l}</span>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn">Bulk approve</button>
              <button className="btn">Bulk reject</button>
            </div>
          </div>
          <table className="ws-table">
            <thead>
              <tr>
                <th>ID</th><th>Type</th><th>Title</th><th>Source</th>
                <th>Ingested</th><th>Conf.</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {reviewQueue.map(r => (
                <tr key={r.id}>
                  <td className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{r.id}</td>
                  <td><span className={"type-pill " + r.t}>{r.t}</span></td>
                  <td>{r.title}</td>
                  <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>{r.src}</td>
                  <td className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{r.ingested}</td>
                  <td className="num">{r.conf}/5</td>
                  <td>
                    <span style={{
                      fontSize: 11, padding: "2px 6px",
                      background: r.status === "auto" ? "#ECF2EC" : r.status === "flagged" ? "#F2ECEC" : "#F0F0F0",
                      color: r.status === "auto" ? "var(--up)" : r.status === "flagged" ? "var(--down)" : "var(--text-secondary)",
                      textTransform: "uppercase", letterSpacing: "0.3px", fontWeight: 500,
                    }}>{r.status}</span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn approve">Approve</button>
                      <button className="btn reject">Reject</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Sources */}
      {tab === "sources" && (
        <div className="ws-card" style={{ padding: 0 }}>
          <table className="ws-table">
            <thead>
              <tr>
                <th>Source</th><th>Type</th><th>Status</th><th>Last ingest</th>
                <th className="num">Facts 7d</th><th className="num">Errors</th><th>Note</th>
              </tr>
            </thead>
            <tbody>
              {sourceRegistry.map(s => (
                <tr key={s.n}>
                  <td style={{ fontWeight: 500 }}>{s.n}</td>
                  <td style={{ color: "var(--text-secondary)" }}>{s.type}</td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: s.status === "healthy" ? "var(--up)" : "var(--down)" }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />
                      {s.status}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{s.lastIngest}</td>
                  <td className="num">{s.facts7d}</td>
                  <td className="num" style={{ color: s.errors > 0 ? "var(--down)" : "var(--text-secondary)" }}>{s.errors}</td>
                  <td style={{ color: "var(--text-secondary)", fontSize: 12, fontStyle: "italic" }}>{s.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Users */}
      {tab === "users" && (
        <div className="ws-card" style={{ padding: 0 }}>
          <table className="ws-table">
            <thead>
              <tr>
                <th>User</th><th>Role</th><th>Organisation</th>
                <th>Last seen</th><th className="num">Seats</th><th></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.n}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{
                        width: 28, height: 28, borderRadius: "50%", background: "var(--brand-navy)",
                        color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 11, fontWeight: 500, fontFamily: "IBM Plex Mono",
                        flexShrink: 0,
                      }}>{initials(u.n)}</div>
                      {u.n}
                    </div>
                  </td>
                  <td>{u.role}</td>
                  <td style={{ color: "var(--text-secondary)" }}>{u.org}</td>
                  <td className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{u.last}</td>
                  <td className="num">{u.seats}</td>
                  <td><button className="btn ghost">Edit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* LLM budget */}
      {tab === "budget" && (
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24 }}>
          <div className="ws-card">
            <div style={{ fontSize: 13, fontWeight: 500 }}>LLM spend — month to date</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4, marginBottom: 18 }}>
              April 2026 · €1,840 of €4,000 monthly cap (46%)
            </div>
            <div style={{ height: 14, background: "#F0F0F0", overflow: "hidden", marginBottom: 24 }}>
              <div style={{ width: "46%", height: "100%", background: "var(--brand-navy)" }} />
            </div>
            <table className="ws-table" style={{ border: "1px solid var(--border)" }}>
              <thead>
                <tr>
                  <th>Capability</th>
                  <th className="num">Calls</th>
                  <th className="num">Tokens (k)</th>
                  <th className="num">Spend €</th>
                </tr>
              </thead>
              <tbody>
                {budgetRows.map((r, i) => (
                  <tr key={i}>
                    <td>{r[0]}</td>
                    <td className="num">{r[1].toLocaleString()}</td>
                    <td className="num">{r[2].toLocaleString()}</td>
                    <td className="num">{r[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ws-card">
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 14 }}>Macro indicators — manual</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 18 }}>
              Override values published on dashboards
            </div>
            {macroOverrides.map((m, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--divider)", alignItems: "center" }}>
                <div style={{ fontSize: 13 }}>{m[0]}</div>
                <div className="tnum" style={{ fontSize: 13, fontWeight: 500 }}>{m[1]}</div>
                <div className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{m[2]}</div>
              </div>
            ))}
            <button className="btn" style={{ width: "100%", marginTop: 14 }}>Update indicators</button>
          </div>
        </div>
      )}
    </div>
  );
}
