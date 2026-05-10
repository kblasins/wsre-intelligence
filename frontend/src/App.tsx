import { useEffect, useState, useCallback } from "react";
import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { BriefsPage } from "./pages/BriefsPage";
import { AdminPage } from "./pages/AdminPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { IntelligencePage } from "./pages/IntelligencePage";
import { CommercialMarketPage } from "./pages/CommercialMarketPage";
import { PrimaryMarketPage } from "./pages/PrimaryMarketPage";
import { SubmarketsPage } from "./pages/SubmarketsPage";
import { formatDate } from "./lib/format";

// ── Auth guard ────────────────────────────────────────────────────────────────

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("ws_token");
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// ── Command bar (⌘K) ─────────────────────────────────────────────────────────

const CMD_ITEMS = [
  { group: "Navigate", label: "Workbench",              kbd: "1", path: "/workbench"   },
  { group: "Navigate", label: "Commercial Market",      kbd: "2", path: "/commercial"  },
  { group: "Navigate", label: "Primary Market",         kbd: "3", path: "/primary"     },
  { group: "Navigate", label: "Submarkets",             kbd: "4", path: "/submarkets"  },
  { group: "Navigate", label: "Briefs",                 kbd: "5", path: "/briefs"      },
  { group: "Navigate", label: "Intelligence Feed",      kbd: "6", path: "/intelligence"},
  { group: "Navigate", label: "Admin",                  kbd: "7", path: "/admin"       },
  { group: "Saved sites", label: "Wola Office Corridor",    kbd: "", path: "/workbench" },
  { group: "Saved sites", label: "Mokotów Służewiec",       kbd: "", path: "/workbench" },
  { group: "Saved sites", label: "Praga-Północ riverfront", kbd: "", path: "/workbench" },
  { group: "Actions", label: "Generate weekly Warsaw brief", kbd: "", path: "/briefs"   },
  { group: "Actions", label: "Open review queue",            kbd: "", path: "/admin"    },
];

function CommandBar({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const items = q
    ? CMD_ITEMS.filter((i) => (i.label + " " + i.group).toLowerCase().includes(q.toLowerCase()))
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
          <input
            className="cmd-input"
            autoFocus
            placeholder="Search sites, screens, actions…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <span className="cmd-kbd">esc</span>
        </div>
        <div className="cmd-list">
          {items.length === 0 && <div className="cmd-empty">No matches.</div>}
          {groups.map((group) => (
            <div className="cmd-group" key={group}>
              <div className="cmd-group-label">{group}</div>
              {items
                .filter((i) => i.group === group)
                .map((item) => (
                  <div
                    key={item.label}
                    className="cmd-item"
                    onClick={() => { navigate(item.path); onClose(); }}
                  >
                    <span>{item.label}</span>
                    {item.kbd && <span className="cmd-kbd">{item.kbd}</span>}
                  </div>
                ))}
            </div>
          ))}
        </div>
        <div className="cmd-foot">
          <span><span className="cmd-kbd">↑↓</span> navigate</span>
          <span><span className="cmd-kbd">↵</span> open</span>
          <span><span className="cmd-kbd">1–7</span> jump to tab</span>
        </div>
      </div>
    </div>
  );
}

// ── App shell ─────────────────────────────────────────────────────────────────

function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [cmdOpen, setCmdOpen] = useState(false);
  const [lang, setLang] = useState<"EN" | "PL">("EN");
  const [marketsOpen, setMarketsOpen] = useState(false);
  const today = formatDate(new Date());

  const openCmd = useCallback(() => setCmdOpen(true), []);

  const inMarkets = location.pathname.startsWith("/commercial") || location.pathname.startsWith("/primary");

  // Keyboard shortcuts: ⌘K / number keys 1-7
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
        return;
      }
      if (cmdOpen) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const paths = ["/workbench", "/commercial", "/primary", "/submarkets", "/briefs", "/intelligence", "/admin"];
      const idx = parseInt(e.key, 10) - 1;
      if (idx >= 0 && idx < paths.length) navigate(paths[idx]!);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cmdOpen, navigate]);

  function handleLogout() {
    localStorage.removeItem("ws_token");
    navigate("/login", { replace: true });
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-page)", display: "flex", flexDirection: "column" }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="ws-header">
        {/* Left: wordmark + context */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 22, height: 22, background: "var(--brand-navy)", color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: "IBM Plex Mono", fontSize: 9, fontWeight: 600, letterSpacing: "0.5px",
            }}>WS</div>
            <span style={{ fontSize: 16, fontWeight: 500, color: "var(--text-heading)" }}>WSRE Intelligence</span>
          </div>
          <div className="ws-vr" />
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Warsaw</span>
        </div>

        {/* Right */}
        <div className="ws-right">
          <span className="ws-date tnum">{today} · CEST</span>

          <div
            className="ws-lang"
            onClick={() => setLang(lang === "EN" ? "PL" : "EN")}
          >
            <span className={lang === "EN" ? "on" : ""}>EN</span>
            <span style={{ margin: "0 2px", color: "var(--text-tertiary)" }}>/</span>
            <span className={lang === "PL" ? "on" : ""}>PL</span>
          </div>

          <button
            onClick={handleLogout}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--text-secondary)", fontFamily: "inherit",
              fontSize: "12px", padding: "3px 10px", cursor: "pointer",
            }}
          >
            Sign out
          </button>

          <div className="ws-avatar">KW</div>
        </div>
      </header>

      {/* ── Nav ────────────────────────────────────────────────────────────── */}
      <nav className="ws-nav">
        <a
          className={"tab" + (location.pathname.startsWith("/workbench") ? " active" : "")}
          onClick={() => navigate("/workbench")}
        >Workbench</a>

        {/* Markets dropdown */}
        <div
          style={{ position: "relative", display: "flex", alignItems: "stretch" }}
          onMouseEnter={() => setMarketsOpen(true)}
          onMouseLeave={() => setMarketsOpen(false)}
        >
          <a
            className={"tab" + (inMarkets ? " active" : "")}
            onClick={() => navigate("/commercial")}
            style={{ display: "flex", alignItems: "center" }}
          >
            Markets <span style={{ marginLeft: 5, fontSize: 9, color: "var(--text-tertiary)" }}>▾</span>
          </a>
          {marketsOpen && (
            <div style={{
              position: "absolute", top: "100%", left: 0, minWidth: 240,
              background: "#fff", border: "1px solid var(--border)",
              borderTop: "2px solid var(--brand-navy)",
              boxShadow: "0 8px 24px rgba(0,0,0,0.06)", zIndex: 50,
            }}>
              {[
                { key: "/commercial", label: "Commercial Market" },
                { key: "/primary", label: "Primary Residential Market" },
              ].map(c => (
                <a
                  key={c.key}
                  onClick={() => { navigate(c.key); setMarketsOpen(false); }}
                  style={{
                    display: "block", padding: "12px 18px", fontSize: 13,
                    color: location.pathname === c.key ? "var(--brand-navy)" : "var(--text-primary)",
                    background: location.pathname === c.key ? "var(--bg-wash)" : "#fff",
                    cursor: "pointer", fontWeight: location.pathname === c.key ? 500 : 400,
                    borderBottom: "1px solid var(--divider)",
                  }}
                >
                  {c.label}
                </a>
              ))}
            </div>
          )}
        </div>

        <a
          className={"tab" + (location.pathname.startsWith("/submarkets") ? " active" : "")}
          onClick={() => navigate("/submarkets")}
        >Submarkets</a>
        <a
          className={"tab" + (location.pathname.startsWith("/briefs") ? " active" : "")}
          onClick={() => navigate("/briefs")}
        >Briefs</a>
        <a
          className={"tab" + (location.pathname.startsWith("/intelligence") ? " active" : "")}
          onClick={() => navigate("/intelligence")}
        >Intelligence Feed</a>
        <a
          className={"tab" + (location.pathname.startsWith("/admin") ? " active" : "")}
          onClick={() => navigate("/admin")}
        >Admin <span className="count">9</span></a>
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
        <Route path="dashboard"    element={<Navigate to="/workbench" replace />} />
        <Route path="workbench"    element={<WorkbenchPage />} />
        <Route path="commercial"   element={<CommercialMarketPage />} />
        <Route path="primary"      element={<PrimaryMarketPage />} />
        <Route path="submarkets"   element={<SubmarketsPage />} />
        <Route path="briefs"       element={<BriefsPage />} />
        <Route path="intelligence" element={<IntelligencePage />} />
        <Route path="admin"        element={<AdminPage />} />
        {/* Legacy redirects */}
        <Route path="industrial"   element={<Navigate to="/commercial" replace />} />
        <Route path="*"            element={<Navigate to="/workbench" replace />} />
      </Route>
    </Routes>
  );
}
