import { useEffect, useState, useCallback } from "react";
import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { BriefsPage } from "./pages/BriefsPage";
import { AdminPage } from "./pages/AdminPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { IntelligencePage } from "./pages/IntelligencePage";
import { IndustrialMarketPage } from "./pages/IndustrialMarketPage";
import { SubmarketsPage } from "./pages/SubmarketsPage";
import { formatDate } from "./lib/format";
import { useBudgetStatus } from "./hooks/useMarketData";

// ── Auth guard ────────────────────────────────────────────────────────────────

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("ws_token");
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// ── Command bar (⌘K) ─────────────────────────────────────────────────────────

const CMD_ITEMS = [
  { group: "Navigate", label: "Workbench",        kbd: "1", path: "/workbench"   },
  { group: "Navigate", label: "Industrial Market", kbd: "2", path: "/industrial"  },
  { group: "Navigate", label: "Submarkets",        kbd: "3", path: "/submarkets"  },
  { group: "Navigate", label: "Briefs",            kbd: "4", path: "/briefs"      },
  { group: "Navigate", label: "Intelligence Feed", kbd: "5", path: "/intelligence"},
  { group: "Navigate", label: "Admin",             kbd: "6", path: "/admin"       },
];

function CommandBar({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const items = q
    ? CMD_ITEMS.filter((i) => i.label.toLowerCase().includes(q.toLowerCase()))
    : CMD_ITEMS;

  const groups = [...new Set(items.map((i) => i.group))];

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="cmd-scrim" onClick={onClose}>
      <div className="cmd-panel" onClick={(e) => e.stopPropagation()}>
        <div className="cmd-input-row">
          <span style={{ color: "var(--text-tertiary)", fontSize: "13px" }}>⌘</span>
          <input
            className="cmd-input"
            autoFocus
            placeholder="Go to page, search saved sites…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <span className="cmd-kbd">ESC</span>
        </div>
        <div className="cmd-list">
          {items.length === 0 && <div className="cmd-empty">No results</div>}
          {groups.map((group) => (
            <div className="cmd-group" key={group}>
              <div className="cmd-group-label">{group}</div>
              {items
                .filter((i) => i.group === group)
                .map((item) => (
                  <div
                    key={item.path}
                    className="cmd-item"
                    onClick={() => { navigate(item.path); onClose(); }}
                  >
                    <span>{item.label}</span>
                    <span className="cmd-kbd">{item.kbd}</span>
                  </div>
                ))}
            </div>
          ))}
        </div>
        <div className="cmd-foot">
          <span><span className="cmd-kbd">↑↓</span> navigate</span>
          <span><span className="cmd-kbd">↵</span> open</span>
          <span><span className="cmd-kbd">ESC</span> close</span>
        </div>
      </div>
    </div>
  );
}

// ── App shell (shared chrome) ─────────────────────────────────────────────────

const NAV_TABS = [
  { label: "Workbench",         path: "/workbench",    kbd: "1" },
  { label: "Industrial Market", path: "/industrial",   kbd: "2" },
  { label: "Submarkets",        path: "/submarkets",   kbd: "3" },
  { label: "Briefs",            path: "/briefs",       kbd: "4" },
  { label: "Intelligence Feed", path: "/intelligence", kbd: "5" },
  { label: "Admin",             path: "/admin",        kbd: "6" },
];

function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [cmdOpen, setCmdOpen] = useState(false);
  const { data: budget } = useBudgetStatus();
  const today = formatDate(new Date());

  const openCmd = useCallback(() => setCmdOpen(true), []);

  // Keyboard shortcuts: ⌘K / number keys 1-6
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
        return;
      }
      if (cmdOpen) return;
      const tab = NAV_TABS.find((t) => t.kbd === e.key);
      if (tab && !e.metaKey && !e.ctrlKey && !e.altKey && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        navigate(tab.path);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cmdOpen, navigate]);

  function handleLogout() {
    localStorage.removeItem("ws_token");
    navigate("/login", { replace: true });
  }

  const activeTab = NAV_TABS.find((t) => location.pathname.startsWith(t.path));

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-page)", display: "flex", flexDirection: "column" }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="ws-header">
        <span className="ws-brand">White Star</span>
        <div className="ws-vr" />
        <span className="ws-context">Riyadh Industrial</span>

        <div className="ws-right">
          {/* Budget indicator */}
          {budget && (
            <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
              <span style={{ color: budget.budget_pct > 80 ? "var(--down)" : "var(--text-primary)" }}>
                ${budget.today_usd.toFixed(2)}
              </span>
              {" / "}${budget.daily_cap_usd}
            </span>
          )}

          {/* ⌘K command bar button */}
          <button className="ws-cmd-btn" onClick={openCmd}>
            <span>Search</span>
            <kbd>⌘K</kbd>
          </button>

          <span className="ws-date">{today}</span>

          <button
            onClick={handleLogout}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--text-secondary)", fontFamily: "inherit",
              fontSize: "12px", padding: "3px 10px", cursor: "pointer",
              borderRadius: "3px",
            }}
          >
            Sign out
          </button>

          <div className="ws-avatar">KW</div>
        </div>
      </header>

      {/* ── Nav ────────────────────────────────────────────────────────────── */}
      <nav className="ws-nav">
        {NAV_TABS.map((tab) => (
          <button
            key={tab.path}
            className={`tab${activeTab?.path === tab.path ? " active" : ""}`}
            onClick={() => navigate(tab.path)}
          >
            {tab.label}
            <span className="count">{tab.kbd}</span>
          </button>
        ))}
      </nav>

      {/* ── Page content ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <Outlet />
      </div>

      {/* ── Command bar overlay ────────────────────────────────────────────── */}
      {cmdOpen && <CommandBar onClose={() => setCmdOpen(false)} />}
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/workbench" replace />} />
        <Route path="dashboard" element={<Navigate to="/industrial" replace />} />
        <Route path="workbench"    element={<WorkbenchPage />} />
        <Route path="industrial"   element={<IndustrialMarketPage />} />
        <Route path="submarkets"   element={<SubmarketsPage />} />
        <Route path="briefs"       element={<BriefsPage />} />
        <Route path="intelligence" element={<IntelligencePage />} />
        <Route path="admin"        element={<AdminPage />} />
        <Route path="*" element={<Navigate to="/workbench" replace />} />
      </Route>
    </Routes>
  );
}
