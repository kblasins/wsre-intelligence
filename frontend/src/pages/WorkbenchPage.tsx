/**
 * WorkbenchPage — Phase 3.5 Spatial Intelligence Workbench
 *
 * Three-pane layout:
 *   Left  (280px) — Saved Sites CRUD list
 *   Center (flex) — MapLibre base map with spatial layers
 *   Right  (360px) — Site Evaluation panel (SSE-streamed results)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type * as GeoJSON from "geojson";
import { useDistrictVelocity } from "../hooks/useMarketData";
import type { VelocityRow } from "../hooks/useMarketData";
import { getStoredLang, setLang } from "../lib/i18n";
import type { Lang } from "../lib/i18n";
import Map, {
  Layer,
  Marker,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

const API_BASE = "/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface SavedSite {
  id: number;
  name: string;
  description: string | null;
  geometry_geojson: string;
  asset_class: string | null;
  target_gfa_sqm: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

interface EvalSection {
  section: string;
  data: Record<string, unknown>;
}

// ── API helpers ────────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("ws_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchSites(): Promise<SavedSite[]> {
  const r = await fetch(`${API_BASE}/spatial/sites`, {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error("Failed to load sites");
  return r.json();
}

async function deleteSite(id: number): Promise<void> {
  const r = await fetch(`${API_BASE}/spatial/sites/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok && r.status !== 204) throw new Error("Delete failed");
}

async function createSite(payload: {
  name: string;
  geometry_geojson: string;
  asset_class?: string;
}): Promise<{ id: number }> {
  const r = await fetch(`${API_BASE}/spatial/sites`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Create failed");
  return r.json();
}

// ── Left rail — Saved Sites ────────────────────────────────────────────────────

function SavedSitesPanel({
  sites,
  selected,
  onSelect,
  onDelete,
  onRefresh,
}: {
  sites: SavedSite[];
  selected: number | null;
  onSelect: (site: SavedSite) => void;
  onDelete: (id: number) => void;
  onRefresh: () => void;
}) {
  const [newName, setNewName] = useState("");
  const [newClass, setNewClass] = useState("");
  const [pinLng, setPinLng] = useState("46.675");
  const [pinLat, setPinLat] = useState("24.688");
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    setMsg(null);
    try {
      const lng = parseFloat(pinLng);
      const lat = parseFloat(pinLat);
      if (isNaN(lng) || isNaN(lat)) {
        setMsg("Invalid coordinates");
        return;
      }
      const geojson = JSON.stringify({
        type: "Point",
        coordinates: [lng, lat],
      });
      await createSite({
        name: newName.trim(),
        geometry_geojson: geojson,
        ...(newClass ? { asset_class: newClass } : {}),
      });
      setNewName("");
      setNewClass("");
      setMsg("Saved");
      onRefresh();
    } catch {
      setMsg("Error saving site");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div
      style={{
        width: "280px",
        flexShrink: 0,
        borderRight: "1px solid var(--color-border-subtle)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--color-border-subtle)",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--color-text-tertiary)",
          }}
        >
          Saved Sites
        </div>
      </div>

      {/* Site list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {sites.length === 0 && (
          <div
            style={{
              padding: "24px 16px",
              fontSize: "11px",
              color: "var(--color-text-tertiary)",
            }}
          >
            No sites saved yet. Drop a pin below.
          </div>
        )}
        {sites.map((s) => (
          <div
            key={s.id}
            onClick={() => onSelect(s)}
            style={{
              padding: "10px 16px",
              borderBottom: "1px solid var(--color-border-subtle)",
              cursor: "pointer",
              background:
                selected === s.id
                  ? "var(--color-bg-elevated)"
                  : "transparent",
              display: "flex",
              alignItems: "flex-start",
              gap: "8px",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--color-text-primary)",
                  fontWeight: selected === s.id ? 600 : 400,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {s.name}
              </div>
              {s.asset_class && (
                <div
                  style={{
                    fontSize: "9px",
                    color: "var(--color-text-tertiary)",
                    marginTop: "2px",
                  }}
                >
                  {s.asset_class}
                </div>
              )}
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s.id);
              }}
              title="Delete site"
              style={{
                background: "transparent",
                border: "none",
                color: "var(--color-text-tertiary)",
                cursor: "pointer",
                fontSize: "12px",
                padding: "0",
                lineHeight: 1,
                flexShrink: 0,
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {/* Create new site */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid var(--color-border-subtle)",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 600,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--color-text-tertiary)",
            marginBottom: "2px",
          }}
        >
          Drop pin
        </div>
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Site name"
          style={inputStyle}
        />
        <div style={{ display: "flex", gap: "6px" }}>
          <input
            value={pinLng}
            onChange={(e) => setPinLng(e.target.value)}
            placeholder="Lon"
            style={{ ...inputStyle, flex: 1 }}
          />
          <input
            value={pinLat}
            onChange={(e) => setPinLat(e.target.value)}
            placeholder="Lat"
            style={{ ...inputStyle, flex: 1 }}
          />
        </div>
        <select
          value={newClass}
          onChange={(e) => setNewClass(e.target.value)}
          style={inputStyle}
        >
          <option value="">Asset class (opt.)</option>
          <option value="warehouse">Warehouse</option>
          <option value="factory">Factory</option>
          <option value="office">Office</option>
          <option value="retail">Retail</option>
          <option value="logistics">Logistics</option>
          <option value="mixed">Mixed-use</option>
        </select>
        <button
          onClick={handleCreate}
          disabled={creating || !newName.trim()}
          style={btnStyle}
        >
          {creating ? "Saving…" : "Save site"}
        </button>
        {msg && (
          <div
            style={{
              fontSize: "10px",
              color:
                msg === "Saved"
                  ? "var(--color-positive)"
                  : "var(--color-negative)",
            }}
          >
            {msg}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Velocity panel — shown when no site is selected ───────────────────────────

function VelocityPanel() {
  const [propType, setPropType] = useState("warehouse");
  const { data: rows = [], isLoading } = useDistrictVelocity(propType);

  const maxCount = rows.reduce((m, r) => Math.max(m, r.tx_count), 1);

  function momentumColor(pct: number | null): string {
    if (pct == null) return "var(--color-text-tertiary)";
    if (pct > 5) return "var(--color-positive)";
    if (pct < -5) return "var(--color-negative)";
    return "var(--color-text-secondary)";
  }

  return (
    <div
      style={{
        width: "360px",
        flexShrink: 0,
        borderLeft: "1px solid var(--color-border-subtle)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--color-border-subtle)",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--color-text-tertiary)",
          }}
        >
          District Velocity · 90d
        </div>
        <div style={{ marginTop: "8px" }}>
          <select
            value={propType}
            onChange={(e) => setPropType(e.target.value)}
            style={inputStyle}
          >
            <option value="warehouse">Warehouse</option>
            <option value="factory">Factory</option>
            <option value="office">Office</option>
            <option value="retail">Retail</option>
          </select>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading && (
          <div style={{ padding: "16px", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
            Loading…
          </div>
        )}
        {!isLoading && rows.length === 0 && (
          <div style={{ padding: "16px", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
            No velocity data yet. Run migration 0009 and refresh.
          </div>
        )}
        {rows.slice(0, 20).map((r) => (
          <div
            key={`${r.district_key}-${r.property_type}`}
            style={{
              padding: "8px 16px",
              borderBottom: "1px solid var(--color-border-subtle)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: "4px",
              }}
            >
              <span
                style={{
                  fontSize: "10px",
                  color: "var(--color-text-primary)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  maxWidth: "200px",
                }}
              >
                {r.district_name}
              </span>
              <span
                style={{
                  fontSize: "10px",
                  fontVariantNumeric: "tabular-nums",
                  color: momentumColor(r.avg_momentum_pct),
                }}
              >
                {r.avg_momentum_pct != null
                  ? `${r.avg_momentum_pct > 0 ? "+" : ""}${r.avg_momentum_pct.toFixed(1)}%`
                  : "—"}
              </span>
            </div>
            {/* Activity bar */}
            <div
              style={{
                height: "3px",
                background: "var(--color-border-subtle)",
                position: "relative",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  height: "100%",
                  width: `${Math.min(100, (r.tx_count / maxCount) * 100)}%`,
                  background: "var(--color-accent)",
                }}
              />
            </div>
            <div
              style={{
                marginTop: "3px",
                fontSize: "9px",
                color: "var(--color-text-tertiary)",
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>{r.tx_count} tx</span>
              {r.avg_price_per_sqm != null && (
                <span>SAR {r.avg_price_per_sqm.toFixed(0)}/sqm</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Right rail — Evaluation panel ─────────────────────────────────────────────

function EvalPanel({
  site,
  adHocGeom,
  onClear,
  onPoiHover,
}: {
  site: SavedSite | null;
  adHocGeom: string | null;
  onClear: () => void;
  onPoiHover: (cat: string | null) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [sections, setSections] = useState<EvalSection[]>([]);
  const [radiusM, setRadiusM] = useState(5000);
  const [timeDays, setTimeDays] = useState(90);

  // Auto-run when adHocGeom changes (map click)
  useEffect(() => {
    if (adHocGeom && !site) {
      void runEvalWithGeom(adHocGeom, null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adHocGeom]);

  async function runEvalWithGeom(geomWkt: string, assetClass: string | null) {
    setLoading(true);
    setSections([]);
    try {
      const r = await fetch(`${API_BASE}/spatial/evaluate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          geometry_wkt: geomWkt,
          radius_m: radiusM,
          time_window_days: timeDays,
          ...(assetClass ? { asset_class: assetClass } : {}),
        }),
      });

      if (!r.ok || !r.body) {
        setSections([{ section: "error", data: { message: "Request failed" } }]);
        return;
      }

      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";
        for (const chunk of lines) {
          const line = chunk.replace(/^data: /, "").trim();
          if (!line) continue;
          try {
            const ev: EvalSection = JSON.parse(line);
            if (ev.section !== "done") {
              // Upsert by section name — prevents duplicate keys if a section
              // is re-sent (e.g. React StrictMode double-invoke).
              setSections((prev) => {
                const idx = prev.findIndex((s) => s.section === ev.section);
                if (idx >= 0) {
                  const next = [...prev];
                  next[idx] = ev;
                  return next;
                }
                return [...prev, ev];
              });
            }
          } catch {
            // skip malformed
          }
        }
      }
    } finally {
      setLoading(false);
    }
  }

  async function runEval() {
    let geomWkt: string;
    let assetClass: string | null = null;

    if (site) {
      let geom = site.geometry_geojson;
      try {
        const parsed = JSON.parse(geom);
        if (parsed.type === "Point") {
          const [lon, lat] = parsed.coordinates;
          geom = `POINT(${lon} ${lat})`;
        }
      } catch {
        // leave as-is
      }
      geomWkt = geom;
      assetClass = site.asset_class ?? null;
    } else if (adHocGeom) {
      geomWkt = adHocGeom;
    } else {
      return;
    }

    await runEvalWithGeom(geomWkt, assetClass);
  }

  return (
    <div
      style={{
        width: "360px",
        flexShrink: 0,
        borderLeft: "1px solid var(--color-border-subtle)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--color-border-subtle)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 600,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--color-text-tertiary)",
            }}
          >
            Evaluation
          </div>
          <div
            style={{
              fontSize: "12px",
              color: "var(--color-text-primary)",
              marginTop: "2px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "220px",
            }}
          >
            {site?.name ?? "Ad-hoc evaluation"}
          </div>
        </div>
        <button
          onClick={onClear}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--color-text-tertiary)",
            cursor: "pointer",
            fontSize: "14px",
          }}
        >
          ×
        </button>
      </div>

      {/* Controls */}
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--color-border-subtle)",
          display: "flex",
          gap: "8px",
          alignItems: "flex-end",
        }}
      >
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Radius (m)</label>
          <select
            value={radiusM}
            onChange={(e) => setRadiusM(Number(e.target.value))}
            style={inputStyle}
          >
            <option value={1000}>1 km</option>
            <option value={2000}>2 km</option>
            <option value={5000}>5 km</option>
            <option value={10000}>10 km</option>
            <option value={20000}>20 km</option>
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Window</label>
          <select
            value={timeDays}
            onChange={(e) => setTimeDays(Number(e.target.value))}
            style={inputStyle}
          >
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>1 year</option>
          </select>
        </div>
        <button
          onClick={runEval}
          disabled={loading}
          style={{ ...btnStyle, flexShrink: 0 }}
        >
          {loading ? "Running…" : "Evaluate"}
        </button>
      </div>

      {/* Results */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {sections.length === 0 && !loading && (
          <div
            style={{
              fontSize: "11px",
              color: "var(--color-text-tertiary)",
            }}
          >
            Press Evaluate to run spatial analysis.
          </div>
        )}
        {loading && sections.length === 0 && (
          <div
            style={{
              fontSize: "11px",
              color: "var(--color-text-tertiary)",
            }}
          >
            Computing…
          </div>
        )}
        {sections.map((s) => (
          <EvalSectionCard key={s.section} section={s} onPoiHover={onPoiHover} />
        ))}
      </div>
    </div>
  );
}

function EvalSectionCard({
  section,
  onPoiHover,
}: {
  section: EvalSection;
  onPoiHover: (cat: string | null) => void;
}) {
  const titles: Record<string, string> = {
    district: "District",
    pois: "Points of Interest",
    regulatory: "Regulatory Zones",
    transactions: "Transaction Comparables",
    listings: "Active Listings",
    reit_properties: "REIT Properties",
    typed_facts: "Intelligence Signal",
    accessibility: "Accessibility",
    macro_context: "Macro Context",
    data_quality: "Data Quality",
  };

  const title = titles[section.section] ?? section.section;
  const d = section.data;

  return (
    <div
      style={{
        marginBottom: "16px",
        border: "1px solid var(--color-border-subtle)",
        background: "var(--color-bg-surface)",
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--color-border-subtle)",
          fontSize: "9px",
          fontWeight: 600,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: "var(--color-text-secondary)",
        }}
      >
        {title}
      </div>
      <div style={{ padding: "10px 12px" }}>
        {section.section === "district" && <DistrictCard d={d} />}
        {section.section === "pois" && <POIsCard d={d} onPoiHover={onPoiHover} />}
        {section.section === "regulatory" && <RegulatoryCard d={d} />}
        {section.section === "transactions" && <StatsCard d={d} prefix="tx" />}
        {section.section === "listings" && <StatsCard d={d} prefix="lst" />}
        {section.section === "reit_properties" && <REITCard d={d} />}
        {section.section === "typed_facts" && <TypedFactsCard d={d} />}
        {section.section === "accessibility" && <AccessibilityCard d={d} />}
        {section.section === "macro_context" && <MacroContextCard d={d} />}
        {section.section === "data_quality" && <DataQualityCard d={d} />}
      </div>
    </div>
  );
}

function DistrictCard({ d }: { d: Record<string, unknown> }) {
  if (!d.found)
    return (
      <div style={noDataStyle}>Outside known district boundaries</div>
    );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <Row label="Name" value={String(d.name_en ?? "—")} />
      {d.name_ar ? <Row label="Arabic" value={String(d.name_ar)} /> : null}
      {d.city ? <Row label="City" value={String(d.city)} /> : null}
      {d.region ? <Row label="Region" value={String(d.region)} /> : null}
    </div>
  );
}

function POIsCard({
  d,
  onPoiHover,
}: {
  d: Record<string, unknown>;
  onPoiHover: (cat: string | null) => void;
}) {
  const cats = (d.by_category ?? []) as Array<{
    category: string;
    count: number;
  }>;
  return (
    <div>
      <div style={{ fontSize: "11px", color: "var(--color-text-secondary)", marginBottom: "8px" }}>
        {String(d.total ?? 0)} POIs within {String(d.radius_m ?? "")}m
      </div>
      {cats.slice(0, 10).map((c) => (
        <div
          key={c.category}
          onMouseEnter={() => onPoiHover(c.category)}
          onMouseLeave={() => onPoiHover(null)}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: "10px",
            color: "var(--color-text-secondary)",
            padding: "3px 4px",
            cursor: "default",
            gap: "6px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <div
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: poiColor(c.category),
                flexShrink: 0,
              }}
            />
            <span style={{ color: "var(--color-text-tertiary)" }}>{c.category}</span>
          </div>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{c.count}</span>
        </div>
      ))}
      {cats.length === 0 && <div style={noDataStyle}>No POIs found</div>}
    </div>
  );
}

function RegulatoryCard({ d }: { d: Record<string, unknown> }) {
  const zones = (d.zones ?? []) as Array<{
    zone_type: string;
    name_en: string;
    effective_from?: string;
    effective_to?: string;
  }>;
  if (zones.length === 0)
    return <div style={noDataStyle}>No regulatory zones intersect this site</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {zones.map((z, i) => (
        <div
          key={i}
          style={{
            padding: "6px 8px",
            background: "var(--color-accent-subtle)",
            border: "1px solid var(--color-accent)",
          }}
        >
          <div style={{ fontSize: "10px", color: "var(--color-accent-bright)" }}>
            {z.zone_type}
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-primary)", marginTop: "2px" }}>
            {z.name_en}
          </div>
          {(z.effective_from || z.effective_to) && (
            <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", marginTop: "2px" }}>
              {z.effective_from ?? "—"} → {z.effective_to ?? "ongoing"}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function StatsCard({
  d,
}: {
  d: Record<string, unknown>;
  prefix: string;
}) {
  const fmt = (v: unknown) =>
    v == null
      ? "—"
      : typeof v === "number"
      ? v >= 1_000_000
        ? `${(v / 1_000_000).toFixed(2)}M`
        : v >= 1_000
        ? `${(v / 1_000).toFixed(1)}K`
        : String(v)
      : String(v);

  const count = d.count as number | undefined;
  const isTransactions = d.time_window_days != null && d.avg_rent_sar_annual == null;
  if (!count)
    return (
      <div style={noDataStyle}>
        {isTransactions
          ? "Limited transaction data available — awaiting REGA Open Data response (submitted 18 Apr 2026)"
          : "No data within search parameters"}
      </div>
    );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <Row label="Count" value={String(count)} />
      {d.avg_price_sar != null && (
        <Row label="Avg price" value={`SAR ${fmt(d.avg_price_sar)}`} />
      )}
      {d.avg_price_per_sqm != null && (
        <Row label="Avg SAR/sqm" value={fmt(d.avg_price_per_sqm)} />
      )}
      {d.avg_rent_sar_annual != null && (
        <Row label="Avg rent/yr" value={`SAR ${fmt(d.avg_rent_sar_annual)}`} />
      )}
      {d.avg_rent_per_sqm != null && (
        <Row label="SAR/sqm/yr" value={fmt(d.avg_rent_per_sqm)} />
      )}
      {d.avg_area_sqm != null && (
        <Row label="Avg area" value={`${fmt(d.avg_area_sqm)} sqm`} />
      )}
    </div>
  );
}

function REITCard({ d }: { d: Record<string, unknown> }) {
  const props = (d.properties ?? []) as Array<{
    ticker: string;
    property_name: string;
    property_type?: string;
    distance_m: number;
    occupancy_pct?: number;
  }>;
  if (props.length === 0)
    return <div style={noDataStyle}>No REIT properties found nearby</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      {props.slice(0, 5).map((p, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "10px",
          }}
        >
          <span style={{ color: "var(--color-text-secondary)" }}>
            [{p.ticker}] {p.property_name.slice(0, 28)}
          </span>
          <span style={{ color: "var(--color-text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
            {Math.round(p.distance_m)}m
          </span>
        </div>
      ))}
      {props.length > 5 && (
        <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)" }}>
          +{props.length - 5} more
        </div>
      )}
    </div>
  );
}

const TABLE_SHORT: Record<string, string> = {
  supply_events: "SUPPLY",
  regulatory_events: "REG",
  macro_signals: "MACRO",
  demand_signals: "DEMAND",
  capital_markets_events: "CAP",
  infrastructure_events: "INFRA",
  tenant_signals: "TENANT",
  market_commentary: "CMMNT",
};

function TypedFactsCard({ d }: { d: Record<string, unknown> }) {
  const facts = (d.facts ?? []) as Array<{
    id: number;
    table: string;
    created_at: string | null;
    confidence: number | null;
    source_citation: string | null;
    summary: string | null;
  }>;
  const count = (d.count as number) ?? 0;
  if (count === 0)
    return <div style={noDataStyle}>No intelligence signal found for this district</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {facts.map((f) => (
        <div
          key={`${f.table}-${f.id}`}
          style={{
            borderLeft: "2px solid var(--color-border-subtle)",
            paddingLeft: "8px",
            display: "flex",
            flexDirection: "column",
            gap: "2px",
          }}
        >
          <div style={{ display: "flex", gap: "6px", alignItems: "baseline" }}>
            <span style={{
              fontSize: "8px",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              color: "var(--color-text-tertiary)",
              letterSpacing: "0.1em",
            }}>
              {TABLE_SHORT[f.table] ?? f.table.toUpperCase()}
            </span>
            {f.confidence != null && (
              <span style={{
                fontSize: "8px",
                color: f.confidence >= 5 ? "#059669" : "#d97706",
                fontFamily: "var(--font-mono)",
              }}>
                c{f.confidence}
              </span>
            )}
            {f.created_at && (
              <span style={{ fontSize: "8px", color: "var(--color-text-tertiary)" }}>
                {new Date(f.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
              </span>
            )}
          </div>
          {f.summary && (
            <div style={{ fontSize: "10px", color: "var(--color-text-secondary)", lineHeight: "1.3" }}>
              {f.summary}
            </div>
          )}
          {f.source_citation && (
            <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", fontStyle: "italic" }}>
              "{f.source_citation.slice(0, 100)}{f.source_citation.length > 100 ? "…" : ""}"
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function AccessibilityCard({ d }: { d: Record<string, unknown> }) {
  if (!d.available) {
    const refs = (d.refs ?? []) as Array<{ key: string; label: string; minutes: null }>;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", fontStyle: "italic", marginBottom: "4px" }}>
          {typeof d.error === "string" ? d.error : "Accessibility data temporarily unavailable."}
        </div>
        {refs.map((r) => (
          <div key={r.key} style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: "10px", color: "var(--color-text-tertiary)" }}>{r.label}</span>
            <span style={{ fontSize: "10px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>--</span>
          </div>
        ))}
      </div>
    );
  }
  const refs = (d.refs ?? []) as Array<{ key: string; label: string; minutes: number | null }>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "2px" }}>
        HGV drive-time
      </div>
      {refs.map((r) => (
        <div key={r.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "8px" }}>
          <span style={{ fontSize: "10px", color: "var(--color-text-secondary)", flex: 1, minWidth: 0 }}>{r.label}</span>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              color: r.minutes != null && r.minutes <= 30
                ? "var(--color-accent-bright)"
                : "var(--color-text-primary)",
              flexShrink: 0,
            }}
          >
            {r.minutes != null ? `${r.minutes} min` : "N/A"}
          </span>
        </div>
      ))}
    </div>
  );
}

function MacroContextCard({ d }: { d: Record<string, unknown> }) {
  if (d.available) {
    const indicators = (d.indicators ?? []) as Array<{
      name: string; value: number; unit: string; period: string | null; source: string;
    }>;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {indicators.map((ind) => (
          <div key={ind.name} style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
            <Row label={ind.name} value={`${ind.value} ${ind.unit}`} />
            {ind.period && (
              <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", textAlign: "right" }}>
                {ind.period} · {ind.source}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }
  // Static reference placeholder
  const ref = d.static_reference as Record<string, unknown> | undefined;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {ref && (
        <>
          <Row
            label="SAMA repo rate"
            value={`${String(ref.sama_repo_rate_pct)}% (${String(ref.as_of)})`}
          />
          {ref.walt_implication && (
            <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", lineHeight: 1.4 }}>
              {String(ref.walt_implication)}
            </div>
          )}
          <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", fontStyle: "italic" }}>
            {String(ref.source ?? "")}
          </div>
        </>
      )}
    </div>
  );
}

function DataQualityCard({ d }: { d: Record<string, unknown> }) {
  const sources = (d.sources ?? []) as Array<{
    name: string; provider: string; last_updated: string | null; status: string; note?: string;
  }>;
  const gaps = (d.gaps ?? []) as string[];
  const statusColor = (s: string) => {
    if (s === "ok") return "var(--color-positive)";
    if (s === "pending" || s === "manual") return "var(--color-accent)";
    return "var(--color-negative)";
  };
  return (
    <div>
      <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
        As of {String(d.as_of ?? "—")} · {String(d.radius_m ?? "—")}m radius
      </div>
      {sources.map((src) => (
        <div
          key={src.name}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "6px",
            padding: "3px 0",
            borderBottom: "1px solid var(--color-border-subtle)",
          }}
        >
          <div
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: statusColor(src.status),
              flexShrink: 0,
              marginTop: "3px",
            }}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "10px", color: "var(--color-text-secondary)" }}>{src.name}</div>
            <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)" }}>
              {src.provider}
              {src.last_updated ? ` · ${src.last_updated}` : ""}
            </div>
            {src.note && (
              <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", fontStyle: "italic" }}>
                {src.note}
              </div>
            )}
          </div>
        </div>
      ))}
      {gaps.length > 0 && (
        <div style={{ marginTop: "8px", fontSize: "9px", color: "var(--color-accent)", fontStyle: "italic" }}>
          Gaps: {gaps.join(", ")}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        fontSize: "10px",
      }}
    >
      <span style={{ color: "var(--color-text-tertiary)" }}>{label}</span>
      <span
        style={{
          color: "var(--color-text-secondary)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </span>
    </div>
  );
}

// ── Shared micro-styles ───────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: "var(--color-bg-input)",
  border: "1px solid var(--color-border-default)",
  color: "var(--color-text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: "10px",
  padding: "4px 6px",
  width: "100%",
  outline: "none",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  background: "var(--color-accent-subtle)",
  border: "1px solid var(--color-accent)",
  color: "var(--color-accent-bright)",
  fontFamily: "var(--font-mono)",
  fontSize: "10px",
  letterSpacing: "0.08em",
  padding: "5px 10px",
  cursor: "pointer",
  textTransform: "uppercase",
};

const labelStyle: React.CSSProperties = {
  fontSize: "9px",
  color: "var(--color-text-tertiary)",
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  display: "block",
  marginBottom: "3px",
};

const noDataStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "var(--color-text-tertiary)",
  fontStyle: "italic",
};

// ── Map center — Riyadh Second Industrial City ────────────────────────────────

const RIYADH_CENTER = { lng: 46.675, lat: 24.688 };

// ── Main WorkbenchPage ────────────────────────────────────────────────────────

// ── Layer toggle state ────────────────────────────────────────────────────────

interface LayerToggles {
  districts: boolean;
  velocity: boolean;
  pois: boolean;
  regulatory: boolean;
  isochrone: boolean;
}

// POI taxonomy: category → subcategories (matches overpass.py CATEGORIES)
const POI_TAXONOMY: Record<string, string[]> = {
  transportation: ["fuel", "parking", "bus", "car_dealer"],
  industrial:     ["warehouse", "data_centre"],
  commercial:     ["mall", "supermarket", "hotel", "restaurant", "cafe", "office_bld", "cowork", "bank", "atm"],
  amenity:        ["hospital", "clinic", "pharmacy", "dental", "gym", "pool", "park", "stadium", "mosque", "cinema", "theatre", "museum", "library"],
  education:      ["nursery", "school", "intl_school", "university"],
  government:     ["govt", "modon", "police", "fire", "post", "embassy"],
  infrastructure: ["power_substation", "water_tower"],
};

// Amenity subcategory groups (for UI separators)
const AMENITY_GROUPS: Record<string, string[]> = {
  health:           ["hospital", "clinic", "pharmacy", "dental"],
  recreation:       ["gym", "pool", "park", "stadium"],
  culture_religion: ["mosque", "cinema", "theatre", "museum", "library"],
};

// Default ON: transportation, industrial, education
function defaultPoiState(): Record<string, boolean> {
  const on = new Set(["transportation", "industrial", "education"]);
  const state: Record<string, boolean> = {};
  for (const [cat, subs] of Object.entries(POI_TAXONOMY)) {
    for (const sub of subs) state[`${cat}/${sub}`] = on.has(cat);
  }
  return state;
}

// Category colors
const POI_CAT_COLORS: Record<string, string> = {
  transportation: "#E8B84A",
  industrial:     "#C9922A",
  commercial:     "#8A7B9A",
  amenity:        "#A07B5E",
  education:      "#5A8A7A",
  government:     "#7B9EA7",
  infrastructure: "#6A6A6A",
};

function poiColor(category: string): string {
  return POI_CAT_COLORS[category] ?? "#888";
}

// Derive whether all/some/none subcategories of a category are active
function catToggleState(cat: string, state: Record<string, boolean>): "all" | "some" | "none" {
  const subs = POI_TAXONOMY[cat] ?? [];
  const count = subs.filter((s) => state[`${cat}/${s}`]).length;
  if (count === subs.length) return "all";
  if (count === 0) return "none";
  return "some";
}

// ── Layer control strip ───────────────────────────────────────────────────────

function LayerControls({
  toggles,
  onChange,
  poiState,
  onPoiSubcat,
  onPoiCat,
  drawMode,
  onDrawMode,
  velocityWindow,
  onVelocityWindow,
  velocityAssetClass,
  onVelocityAssetClass,
  isoProfile,
  onIsoProfile,
  isoError,
}: {
  toggles: LayerToggles;
  onChange: (k: keyof LayerToggles, v: boolean) => void;
  poiState: Record<string, boolean>;
  onPoiSubcat: (key: string, v: boolean) => void;
  onPoiCat: (cat: string, v: boolean) => void;
  drawMode: boolean;
  onDrawMode: (v: boolean) => void;
  velocityWindow: number;
  onVelocityWindow: (d: number) => void;
  velocityAssetClass: string;
  onVelocityAssetClass: (c: string) => void;
  isoProfile: "driving-hgv" | "driving-car";
  onIsoProfile: (p: "driving-hgv" | "driving-car") => void;
  isoError: string | null;
}) {
  const [poiExpanded, setPoiExpanded] = useState(false);
  const [velocityExpanded, setVelocityExpanded] = useState(false);
  const [isoExpanded, setIsoExpanded] = useState(false);
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({});

  const toggleBtn = (
    active: boolean,
    label: string,
    onClick: () => void,
  ) => (
    <button
      onClick={onClick}
      style={{
        background: active ? "rgba(201,146,42,0.9)" : "rgba(20,19,16,0.85)",
        border: "1px solid var(--color-border-default)",
        color: active ? "var(--color-bg-canvas)" : "var(--color-text-tertiary)",
        fontFamily: "var(--font-mono)",
        fontSize: "9px",
        letterSpacing: "0.1em",
        padding: "4px 8px",
        cursor: "pointer",
        textTransform: "uppercase",
        textAlign: "left",
        minWidth: "90px",
      }}
    >
      {label}
    </button>
  );

  return (
    <div
      style={{
        position: "absolute",
        top: "12px",
        left: "12px",
        zIndex: 2,
        display: "flex",
        flexDirection: "column",
        gap: "4px",
      }}
    >
      {toggleBtn(toggles.districts, "Districts", () => onChange("districts", !toggles.districts))}

      {/* Velocity heatmap toggle with controls */}
      <div>
        <div style={{ display: "flex", gap: "2px" }}>
          {toggleBtn(toggles.velocity, "Velocity", () => onChange("velocity", !toggles.velocity))}
          <button
            onClick={() => setVelocityExpanded((v) => !v)}
            style={{
              background: "rgba(20,19,16,0.85)",
              border: "1px solid var(--color-border-default)",
              color: "var(--color-text-tertiary)",
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              padding: "4px 6px",
              cursor: "pointer",
            }}
            title="Velocity options"
          >
            {velocityExpanded ? "▲" : "▼"}
          </button>
        </div>
        {velocityExpanded && (
          <div
            style={{
              background: "rgba(20,19,16,0.9)",
              border: "1px solid var(--color-border-default)",
              padding: "6px 8px",
              display: "flex",
              flexDirection: "column",
              gap: "5px",
              marginTop: "2px",
            }}
          >
            <div style={{ fontSize: "8px", color: "var(--color-text-tertiary)", letterSpacing: "0.1em", textTransform: "uppercase" }}>Window</div>
            <div style={{ display: "flex", gap: "3px" }}>
              {[30, 90, 365].map((d) => (
                <button
                  key={d}
                  onClick={() => onVelocityWindow(d)}
                  style={{
                    background: velocityWindow === d ? "rgba(201,146,42,0.7)" : "rgba(20,19,16,0.7)",
                    border: "1px solid var(--color-border-default)",
                    color: velocityWindow === d ? "var(--color-bg-canvas)" : "var(--color-text-tertiary)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "8px",
                    padding: "2px 5px",
                    cursor: "pointer",
                  }}
                >
                  {d === 365 ? "365d" : `${d}d`}
                </button>
              ))}
            </div>
            <div style={{ fontSize: "8px", color: "var(--color-text-tertiary)", letterSpacing: "0.1em", textTransform: "uppercase", marginTop: "2px" }}>Asset class</div>
            <select
              value={velocityAssetClass}
              onChange={(e) => onVelocityAssetClass(e.target.value)}
              style={{
                background: "rgba(20,19,16,0.7)",
                border: "1px solid var(--color-border-default)",
                color: "var(--color-text-secondary)",
                fontFamily: "var(--font-mono)",
                fontSize: "8px",
                padding: "2px 4px",
                width: "100%",
              }}
            >
              <option value="">All</option>
              <option value="warehouse">Warehouse</option>
              <option value="factory">Factory</option>
              <option value="office">Office</option>
              <option value="retail">Retail</option>
              <option value="residential">Residential</option>
            </select>
          </div>
        )}
      </div>

      {/* POI toggle with collapsible category tree */}
      <div>
        <div style={{ display: "flex", gap: "2px" }}>
          {toggleBtn(toggles.pois, "POIs", () => onChange("pois", !toggles.pois))}
          <button
            onClick={() => setPoiExpanded((v) => !v)}
            style={{
              background: "rgba(20,19,16,0.85)",
              border: "1px solid var(--color-border-default)",
              color: "var(--color-text-tertiary)",
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              padding: "4px 6px",
              cursor: "pointer",
            }}
            title="Toggle per-category"
          >
            {poiExpanded ? "▲" : "▼"}
          </button>
        </div>
        {poiExpanded && (
          <div
            style={{
              background: "rgba(20,19,16,0.9)",
              border: "1px solid var(--color-border-default)",
              padding: "6px 8px",
              marginTop: "2px",
              display: "flex",
              flexDirection: "column",
              gap: "2px",
            }}
          >
            {Object.keys(POI_TAXONOMY).map((cat) => {
              const ts = catToggleState(cat, poiState);
              const catOpen = openCats[cat] ?? false;
              const subs = POI_TAXONOMY[cat]!;
              const amenityGroups = cat === "amenity" ? AMENITY_GROUPS : null;
              return (
                <div key={cat}>
                  {/* Category row */}
                  <div style={{ display: "flex", alignItems: "center", gap: "4px", marginBottom: "1px" }}>
                    <input
                      type="checkbox"
                      ref={(el) => {
                        if (el) el.indeterminate = ts === "some";
                      }}
                      checked={ts === "all"}
                      onChange={(e) => onPoiCat(cat, e.target.checked)}
                      style={{ accentColor: poiColor(cat), margin: 0, flexShrink: 0 }}
                    />
                    <div
                      style={{
                        width: "6px",
                        height: "6px",
                        borderRadius: "50%",
                        background: poiColor(cat),
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontSize: "9px",
                        fontFamily: "var(--font-mono)",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                        color: ts !== "none" ? "var(--color-text-secondary)" : "var(--color-text-tertiary)",
                        flex: 1,
                        cursor: "pointer",
                        userSelect: "none",
                      }}
                      onClick={() => setOpenCats((prev) => ({ ...prev, [cat]: !(prev[cat] ?? false) }))}
                    >
                      {cat}
                    </span>
                    <button
                      onClick={() => setOpenCats((prev) => ({ ...prev, [cat]: !(prev[cat] ?? false) }))}
                      style={{
                        background: "none",
                        border: "none",
                        color: "var(--color-text-tertiary)",
                        fontSize: "8px",
                        padding: "0 2px",
                        cursor: "pointer",
                        lineHeight: 1,
                      }}
                    >
                      {catOpen ? "▲" : "▼"}
                    </button>
                  </div>
                  {/* Subcategory rows */}
                  {catOpen && (
                    <div style={{ paddingLeft: "16px", display: "flex", flexDirection: "column", gap: "2px", marginBottom: "4px" }}>
                      {amenityGroups
                        ? Object.entries(amenityGroups).map(([group, groupSubs], gi) => (
                          <div key={group}>
                            {gi > 0 && (
                              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "3px 0" }} />
                            )}
                            <div style={{ fontSize: "8px", color: "var(--color-text-tertiary)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "2px", fontFamily: "var(--font-mono)" }}>
                              {group.replace("_", " ")}
                            </div>
                            {groupSubs.map((sub) => (
                              <label key={sub} style={{ display: "flex", alignItems: "center", gap: "5px", cursor: "pointer" }}>
                                <input
                                  type="checkbox"
                                  checked={poiState[`${cat}/${sub}`] ?? false}
                                  onChange={(e) => onPoiSubcat(`${cat}/${sub}`, e.target.checked)}
                                  style={{ accentColor: poiColor(cat), margin: 0 }}
                                />
                                <span style={{ fontSize: "9px", fontFamily: "var(--font-mono)", color: poiState[`${cat}/${sub}`] ? "var(--color-text-secondary)" : "var(--color-text-tertiary)" }}>
                                  {sub.replace(/_/g, " ")}
                                </span>
                              </label>
                            ))}
                          </div>
                        ))
                        : subs.map((sub) => (
                          <label key={sub} style={{ display: "flex", alignItems: "center", gap: "5px", cursor: "pointer" }}>
                            <input
                              type="checkbox"
                              checked={poiState[`${cat}/${sub}`] ?? false}
                              onChange={(e) => onPoiSubcat(`${cat}/${sub}`, e.target.checked)}
                              style={{ accentColor: poiColor(cat), margin: 0 }}
                            />
                            <span style={{ fontSize: "9px", fontFamily: "var(--font-mono)", color: poiState[`${cat}/${sub}`] ? "var(--color-text-secondary)" : "var(--color-text-tertiary)" }}>
                              {sub.replace(/_/g, " ")}
                            </span>
                          </label>
                        ))
                      }
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {toggleBtn(toggles.regulatory, "Regulatory", () => onChange("regulatory", !toggles.regulatory))}

      {/* Isochrone toggle with profile selector */}
      <div>
        <div style={{ display: "flex", gap: "2px" }}>
          {toggleBtn(toggles.isochrone, "Isochrone", () => onChange("isochrone", !toggles.isochrone))}
          <button
            onClick={() => setIsoExpanded((v) => !v)}
            style={{
              background: "rgba(20,19,16,0.85)",
              border: "1px solid var(--color-border-default)",
              color: "var(--color-text-tertiary)",
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              padding: "4px 6px",
              cursor: "pointer",
            }}
            title="Isochrone options"
          >
            {isoExpanded ? "▲" : "▼"}
          </button>
        </div>
        {isoExpanded && (
          <div
            style={{
              background: "rgba(20,19,16,0.9)",
              border: "1px solid var(--color-border-default)",
              padding: "6px 8px",
              display: "flex",
              flexDirection: "column",
              gap: "5px",
              marginTop: "2px",
            }}
          >
            <div style={{ fontSize: "8px", color: "var(--color-text-tertiary)", letterSpacing: "0.1em", textTransform: "uppercase" }}>Profile</div>
            <div style={{ display: "flex", gap: "3px" }}>
              {(["driving-hgv", "driving-car"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => onIsoProfile(p)}
                  style={{
                    background: isoProfile === p ? "rgba(201,146,42,0.7)" : "rgba(20,19,16,0.7)",
                    border: "1px solid var(--color-border-default)",
                    color: isoProfile === p ? "var(--color-bg-canvas)" : "var(--color-text-tertiary)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "8px",
                    padding: "2px 5px",
                    cursor: "pointer",
                  }}
                >
                  {p === "driving-hgv" ? "HGV" : "Car"}
                </button>
              ))}
            </div>
            {isoError && (
              <div style={{ fontSize: "8px", color: "var(--color-text-tertiary)", fontStyle: "italic" }}>
                ORS unavailable — isochrone not loaded
              </div>
            )}
          </div>
        )}
      </div>

      {toggleBtn(drawMode, drawMode ? "Draw: on" : "Draw polygon", () => onDrawMode(!drawMode))}
    </div>
  );
}

export function WorkbenchPage() {
  const mapRef = useRef<MapRef>(null);
  const [sites, setSites] = useState<SavedSite[]>([]);
  const [selectedSite, setSelectedSite] = useState<SavedSite | null>(null);
  // Ad-hoc evaluation state (map click or polygon draw, not a saved site)
  const [adHocGeom, setAdHocGeom] = useState<string | null>(null);
  const [lang, setLangState] = useState<Lang>(getStoredLang);

  function toggleLang() {
    const next: Lang = lang === "en" ? "ar" : "en";
    setLang(next);
    setLangState(next);
  }
  const [markerCoords, setMarkerCoords] = useState<{
    lng: number;
    lat: number;
  } | null>(null);

  // Polygon draw state
  const [drawMode, setDrawMode] = useState(false);
  const [drawVertices, setDrawVertices] = useState<[number, number][]>([]);

  // POI hover state (category name or null)
  const [hoveredPoiCat, setHoveredPoiCat] = useState<string | null>(null);
  const [poiPopup, setPoiPopup] = useState<{
    lng: number; lat: number;
    name_en: string | null; name_ar: string | null;
    address: string | null;
    category: string; subcategory: string;
    operator: string | null; brand: string | null;
    phone: string | null; website: string | null;
    opening_hours: string | null;
    building_levels: number | null; height_m: number | null;
    capacity: number | null; footprint_area_sqm: number | null;
    last_seen_at: string | null;
  } | null>(null);

  // Layer data
  const [districtGeoJSON, setDistrictGeoJSON] = useState<object | null>(null);
  const [poiGeoJSON, setPoiGeoJSON] = useState<object | null>(null);
  const [regulatoryGeoJSON, setRegulatoryGeoJSON] = useState<object | null>(null);
  const [isochroneGeoJSON, setIsochroneGeoJSON] = useState<object | null>(null);
  const [isoProfile, setIsoProfile] = useState<"driving-hgv" | "driving-car">("driving-hgv");
  const [isoError, setIsoError] = useState<string | null>(null);

  const [toggles, setToggles] = useState<LayerToggles>({
    districts: true,
    velocity: false,
    pois: true,
    regulatory: false,
    isochrone: false,
  });

  // Velocity heatmap controls
  const [velocityWindow, setVelocityWindow] = useState(90);
  const [velocityAssetClass, setVelocityAssetClass] = useState("");
  const [velocityTooltip, setVelocityTooltip] = useState<{
    x: number; y: number;
    district: string; districtAr: string | null;
    txCount: number; pricePerSqm: number | null; latestMonth: string | null;
  } | null>(null);

  const { data: velocityRows = [] } = useDistrictVelocity(
    velocityAssetClass || undefined,
    velocityWindow,
  );

  // Build a lookup from district_key → velocity row
  const velocityByKey = useMemo((): Record<string, VelocityRow> => {
    const m: Record<string, VelocityRow> = {};
    for (const row of velocityRows) {
      m[row.district_key] = row;
    }
    return m;
  }, [velocityRows]);

  // Max tx_count for normalizing color scale
  const maxTxCount = useMemo(
    () => Math.max(1, ...velocityRows.map((r) => r.tx_count)),
    [velocityRows],
  );

  // Velocity GeoJSON: district polygons annotated with tx_count
  const velocityGeoJSON = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!districtGeoJSON || !toggles.velocity) return null;
    const fc = districtGeoJSON as GeoJSON.FeatureCollection;
    const features = fc.features.map((f) => {
      const id = String((f.properties as Record<string, unknown>)?.id ?? "");
      const row = velocityByKey[id];
      return {
        ...f,
        properties: {
          ...(f.properties as Record<string, unknown>),
          tx_count: row?.tx_count ?? 0,
          avg_price_per_sqm: row?.avg_price_per_sqm ?? null,
          avg_momentum_pct: row?.avg_momentum_pct ?? null,
          latest_month: row?.latest_month ?? null,
          has_data: row != null,
        },
      };
    });
    return { type: "FeatureCollection", features };
  }, [districtGeoJSON, velocityByKey, toggles.velocity]);

  const [poiState, setPoiState] = useState<Record<string, boolean>>(defaultPoiState);

  function setToggle(k: keyof LayerToggles, v: boolean) {
    setToggles((prev) => ({ ...prev, [k]: v }));
  }

  function setPoiSubcat(key: string, v: boolean) {
    setPoiState((prev) => ({ ...prev, [key]: v }));
  }

  function setPoiCat(cat: string, v: boolean) {
    setPoiState((prev) => {
      const next = { ...prev };
      for (const sub of POI_TAXONOMY[cat] ?? []) next[`${cat}/${sub}`] = v;
      return next;
    });
  }

  // Fetch district polygons once on mount
  useEffect(() => {
    fetch(`${API_BASE}/spatial/districts/geojson`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setDistrictGeoJSON(d); })
      .catch(() => {});
  }, []);

  // Fetch POIs when layer enabled
  useEffect(() => {
    if (!toggles.pois || poiGeoJSON) return;
    fetch(`${API_BASE}/spatial/pois/geojson?limit=5000`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setPoiGeoJSON(d); })
      .catch(() => {});
  }, [toggles.pois, poiGeoJSON]);

  // Fetch regulatory zones when layer enabled
  useEffect(() => {
    if (!toggles.regulatory || regulatoryGeoJSON) return;
    fetch(`${API_BASE}/spatial/regulatory-zones/geojson`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setRegulatoryGeoJSON(d); })
      .catch(() => {});
  }, [toggles.regulatory, regulatoryGeoJSON]);

  // Fetch isochrone for selected site when layer enabled or profile changes
  useEffect(() => {
    if (!toggles.isochrone || !markerCoords) return;
    const { lng, lat } = markerCoords;
    setIsoError(null);
    fetch(`${API_BASE}/spatial/isochrone?lon=${lng}&lat=${lat}&profile=${isoProfile}`, {
      headers: authHeaders(),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((d) => { if (d) setIsochroneGeoJSON(d); })
      .catch((e: unknown) => {
        setIsoError(e instanceof Error ? e.message : "ORS unavailable");
      });
  }, [toggles.isochrone, markerCoords, isoProfile]);

  const loadSites = useCallback(async () => {
    try {
      const data = await fetchSites();
      setSites(data);
      // Auto-select the first site on initial load if nothing is selected yet
      if (data.length > 0) {
        setSelectedSite((prev) => prev ?? data[0] ?? null);
      }
    } catch {
      // silently fail — user may not be authenticated yet
    }
  }, []);

  useEffect(() => {
    loadSites();
  }, [loadSites]);

  function handleSelectSite(site: SavedSite) {
    setSelectedSite(site);
    setAdHocGeom(null);
    setDrawMode(false);
    setDrawVertices([]);
    setIsochroneGeoJSON(null); // clear stale isochrone
    try {
      const geom = JSON.parse(site.geometry_geojson);
      if (geom.type === "Point" && mapRef.current) {
        mapRef.current.flyTo({
          center: [geom.coordinates[0], geom.coordinates[1]],
          zoom: 14,
          duration: 800,
        });
        setMarkerCoords({ lng: geom.coordinates[0], lat: geom.coordinates[1] });
      }
    } catch {
      // non-point geometry
    }
  }

  function handleMapClick(e: MapLayerMouseEvent) {
    if (drawMode) {
      setDrawVertices((prev) => [...prev, [e.lngLat.lng, e.lngLat.lat]]);
      return;
    }
    // Check if a POI dot was clicked
    const map = mapRef.current?.getMap();
    if (map && toggles.pois) {
      const feats = map.queryRenderedFeatures(e.point, { layers: ["poi-dots"] });
      if (feats?.length) {
        const f = feats[0]!;
        const p = f.properties as Record<string, string | null>;
        setPoiPopup({
          lng: e.lngLat.lng,
          lat: e.lngLat.lat,
          name_en: p["name_en"] ?? null,
          name_ar: p["name_ar"] ?? null,
          address: p["address"] ?? null,
          category: p["category"] ?? "",
          subcategory: p["subcategory"] ?? "",
          operator: p["operator"] ?? null,
          brand: p["brand"] ?? null,
          phone: p["phone"] ?? null,
          website: p["website"] ?? null,
          opening_hours: p["opening_hours"] ?? null,
          building_levels: p["building_levels"] != null ? Number(p["building_levels"]) : null,
          height_m: p["height_m"] != null ? Number(p["height_m"]) : null,
          capacity: p["capacity"] != null ? Number(p["capacity"]) : null,
          footprint_area_sqm: p["footprint_area_sqm"] != null ? Number(p["footprint_area_sqm"]) : null,
          last_seen_at: p["last_seen_at"] ?? null,
        });
        return;
      }
    }
    // No POI hit — dismiss any open popup and run point evaluate
    setPoiPopup(null);
    setSelectedSite(null);
    setIsochroneGeoJSON(null);
    setMarkerCoords({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    setAdHocGeom(`POINT(${e.lngLat.lng} ${e.lngLat.lat})`);
  }

  function handleMapDblClick(e: { lngLat: { lng: number; lat: number } }) {
    if (!drawMode || drawVertices.length < 3) return;
    // Close polygon on double-click
    const verts = [...drawVertices, [e.lngLat.lng, e.lngLat.lat]];
    const ring = [...verts, verts[0]] as [number, number][]; // close ring
    const coordStr = ring.map(([x, y]) => `${x} ${y}`).join(", ");
    const polygonWkt = `POLYGON((${coordStr}))`;
    setAdHocGeom(polygonWkt);
    setSelectedSite(null);
    setMarkerCoords(null);
    setDrawMode(false);
    setDrawVertices([]);
    setIsochroneGeoJSON(null);
  }

  async function handleDelete(id: number) {
    await deleteSite(id);
    if (selectedSite?.id === id) {
      setSelectedSite(null);
      setAdHocGeom(null);
      setMarkerCoords(null);
      setIsochroneGeoJSON(null);
    }
    loadSites();
  }

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-page)",
        overflow: "hidden",
      }}
    >
      {/* Workbench toolbar */}
      <div
        style={{
          height: "40px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          padding: "0 20px",
          gap: "20px",
          flexShrink: 0,
          background: "var(--bg-surface)",
        }}
      >
        <span
          style={{
            fontSize: "11px",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            color: "var(--text-secondary)",
          }}
        >
          Site Workbench
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "16px" }}>
          <button
            onClick={toggleLang}
            style={{
              fontSize: "11px",
              color: "var(--text-secondary)",
              background: "none",
              border: "1px solid var(--border)",
              padding: "2px 8px",
              cursor: "pointer",
              fontFamily: "inherit",
              borderRadius: "3px",
            }}
          >
            {lang === "en" ? "AR" : "EN"}
          </button>
          <span style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>
            Riyadh Metro · WGS-84
          </span>
        </div>
      </div>

      {/* Three-pane body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Left: Saved Sites */}
        <SavedSitesPanel
          sites={sites}
          selected={selectedSite?.id ?? null}
          onSelect={handleSelectSite}
          onDelete={handleDelete}
          onRefresh={loadSites}
        />

        {/* Center: Map */}
        <div style={{ flex: 1, position: "relative" }}>
          <Map
            ref={mapRef}
            initialViewState={{
              longitude: RIYADH_CENTER.lng,
              latitude: RIYADH_CENTER.lat,
              zoom: 12,
            }}
            style={{ width: "100%", height: "100%", cursor: drawMode ? "crosshair" : "grab" }}
            mapStyle="https://tiles.openfreemap.org/styles/liberty"
            onClick={handleMapClick}
            onDblClick={handleMapDblClick}
            onMouseMove={(e) => {
              if (!toggles.velocity || !velocityGeoJSON) { setVelocityTooltip(null); return; }
              const map = mapRef.current?.getMap();
              if (!map) return;
              const feats = map.queryRenderedFeatures(e.point, { layers: ["velocity-fill"] });
              if (!feats?.length) { setVelocityTooltip(null); return; }
              const feat = feats[0];
              if (!feat) { setVelocityTooltip(null); return; }
              const p = (feat.properties ?? {}) as Record<string, unknown>;
              if (!p || !p.has_data) { setVelocityTooltip(null); return; }
              setVelocityTooltip({
                x: e.point.x,
                y: e.point.y,
                district: String(p.name_en ?? ""),
                districtAr: p.name_ar ? String(p.name_ar) : null,
                txCount: Number(p.tx_count ?? 0),
                pricePerSqm: p.avg_price_per_sqm != null ? Number(p.avg_price_per_sqm) : null,
                latestMonth: p.latest_month ? String(p.latest_month) : null,
              });
            }}
            onMouseLeave={() => setVelocityTooltip(null)}
          >
            <NavigationControl position="top-right" />

            {/* ── District polygon layer ─────────────────────────────────── */}
            {districtGeoJSON && toggles.districts && (
              <Source id="districts" type="geojson" data={districtGeoJSON as GeoJSON.FeatureCollection}>
                <Layer
                  id="districts-fill"
                  type="fill"
                  paint={{
                    "fill-color": "#C9922A",
                    "fill-opacity": 0.06,
                  }}
                />
                <Layer
                  id="districts-outline"
                  type="line"
                  paint={{
                    "line-color": "#C9922A",
                    "line-width": 1,
                    "line-opacity": 0.5,
                  }}
                />
                {/* ── Bilingual district labels ── */}
                <Layer
                  id="districts-labels"
                  type="symbol"
                  layout={{
                    "text-field": ["get", lang === "ar" ? "name_ar" : "name_en"],
                    "text-size": 10,
                    "text-font": ["Noto Sans Regular"],
                    "text-anchor": "center",
                    "text-max-width": 8,
                  }}
                  paint={{
                    "text-color": "#C9922A",
                    "text-opacity": 0.7,
                    "text-halo-color": "#0D0C0A",
                    "text-halo-width": 1,
                  }}
                />
              </Source>
            )}

            {/* ── Velocity heatmap layer ────────────────────────────────── */}
            {velocityGeoJSON && toggles.velocity && (
              <Source id="velocity" type="geojson" data={velocityGeoJSON}>
                <Layer
                  id="velocity-fill"
                  type="fill"
                  paint={{
                    "fill-color": [
                      "case",
                      ["!", ["get", "has_data"]], "rgba(0,0,0,0)",
                      [
                        "interpolate", ["linear"],
                        ["get", "tx_count"],
                        0,  "rgba(201,146,42,0.05)",
                        5,  "rgba(201,146,42,0.2)",
                        15, "rgba(201,146,42,0.4)",
                        30, "rgba(201,146,42,0.65)",
                        60, "rgba(201,146,42,0.85)",
                      ],
                    ],
                    "fill-opacity": 1,
                  }}
                />
                <Layer
                  id="velocity-outline"
                  type="line"
                  filter={["==", ["get", "has_data"], true]}
                  paint={{
                    "line-color": "rgba(201,146,42,0.5)",
                    "line-width": 1,
                  }}
                />
              </Source>
            )}

            {/* ── POI layer (per-category filtering + hover emphasis) ────── */}
            {poiGeoJSON && toggles.pois && (() => {
              // Build subcategory filter from poiState
              const activeSubcats = Object.entries(poiState)
                .filter(([, v]) => v)
                .map(([key]) => key.split("/")[1]!);
              const catFilter: unknown[] = activeSubcats.length > 0
                ? ["in", ["get", "subcategory"], ["literal", activeSubcats]]
                : ["==", 1, 0]; // no active subcats → show nothing

              return (
                <Source
                  id="pois"
                  type="geojson"
                  data={poiGeoJSON as GeoJSON.FeatureCollection}
                >
                  {/* POI dots — filtered by active subcategories */}
                  <Layer
                    id="poi-dots"
                    type="circle"
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    filter={catFilter as any}
                    paint={{
                      "circle-color": [
                        "match",
                        ["get", "category"],
                        "transportation", "#E8B84A",
                        "industrial",     "#C9922A",
                        "commercial",     "#8A7B9A",
                        "amenity",        "#A07B5E",
                        "education",      "#5A8A7A",
                        "government",     "#7B9EA7",
                        "infrastructure", "#6A6A6A",
                        "#888888",
                      ],
                      // Always-expression form avoids MapLibre type-switch errors
                      // when hoveredPoiCat toggles between null and a string.
                      "circle-radius": ["case",
                        ["==", ["get", "category"], hoveredPoiCat ?? ""], 7, 4,
                      ],
                      "circle-opacity": ["case",
                        ["==", ["get", "category"], hoveredPoiCat ?? ""], 1.0, 0.8,
                      ],
                      "circle-stroke-width": ["case",
                        ["==", ["get", "category"], hoveredPoiCat ?? ""], 2, 1,
                      ],
                      "circle-stroke-color": "#0D0C0A",
                    }}
                  />
                </Source>
              );
            })()}

            {/* ── Regulatory zone hatched fill ──────────────────────────── */}
            {regulatoryGeoJSON && toggles.regulatory && (
              <Source id="regulatory" type="geojson" data={regulatoryGeoJSON as GeoJSON.FeatureCollection}>
                <Layer
                  id="regulatory-fill"
                  type="fill"
                  paint={{
                    "fill-color": "#D45252",
                    "fill-opacity": 0.12,
                  }}
                />
                <Layer
                  id="regulatory-outline"
                  type="line"
                  paint={{
                    "line-color": "#D45252",
                    "line-width": 1.5,
                    "line-opacity": 0.8,
                    "line-dasharray": [4, 2],
                  }}
                />
              </Source>
            )}

            {/* ── Isochrone rings ────────────────────────────────────────── */}
            {isochroneGeoJSON && toggles.isochrone && (
              <Source id="isochrone" type="geojson" data={isochroneGeoJSON as GeoJSON.FeatureCollection}>
                <Layer
                  id="isochrone-fill"
                  type="fill"
                  paint={{
                    "fill-color": [
                      "match",
                      ["get", "minutes"],
                      15, "#4DB87A",
                      30, "#E8B84A",
                      60, "#D45252",
                      "#888888",
                    ],
                    "fill-opacity": 0.1,
                  }}
                />
                <Layer
                  id="isochrone-outline"
                  type="line"
                  paint={{
                    "line-color": [
                      "match",
                      ["get", "minutes"],
                      15, "#4DB87A",
                      30, "#E8B84A",
                      60, "#D45252",
                      "#888888",
                    ],
                    "line-width": 1.5,
                    "line-opacity": 0.7,
                  }}
                />
              </Source>
            )}

            {/* ── Draw polygon preview vertices ──────────────────────────── */}
            {drawMode && drawVertices.length > 0 && (() => {
              const previewGeojson: GeoJSON.FeatureCollection = {
                type: "FeatureCollection",
                features: [
                  {
                    type: "Feature",
                    geometry: {
                      type: "LineString",
                      coordinates: drawVertices,
                    },
                    properties: {},
                  },
                  ...drawVertices.map(([lng, lat], i) => ({
                    type: "Feature" as const,
                    geometry: { type: "Point" as const, coordinates: [lng, lat] },
                    properties: { i },
                  })),
                ],
              };
              return (
                <Source id="draw-preview" type="geojson" data={previewGeojson}>
                  <Layer
                    id="draw-line"
                    type="line"
                    filter={["==", ["geometry-type"], "LineString"]}
                    paint={{ "line-color": "#C9922A", "line-width": 2, "line-dasharray": [3, 2] }}
                  />
                  <Layer
                    id="draw-verts"
                    type="circle"
                    filter={["==", ["geometry-type"], "Point"]}
                    paint={{ "circle-color": "#C9922A", "circle-radius": 5, "circle-stroke-width": 1, "circle-stroke-color": "#fff" }}
                  />
                </Source>
              );
            })()}

            {/* ── Selected site marker (on top of layers) ───────────────── */}
            {markerCoords && (
              <Marker longitude={markerCoords.lng} latitude={markerCoords.lat}>
                <div
                  style={{
                    width: "14px",
                    height: "14px",
                    borderRadius: "50%",
                    background: "var(--color-accent)",
                    border: "2px solid var(--color-accent-bright)",
                    boxShadow: "0 0 6px rgba(201,146,42,0.8)",
                  }}
                />
              </Marker>
            )}

            {/* ── All saved sites as markers ─────────────────────────────── */}
            {sites.map((s) => {
              try {
                const geom = JSON.parse(s.geometry_geojson);
                if (geom.type !== "Point") return null;
                const [lng, lat] = geom.coordinates;
                return (
                  <Marker
                    key={s.id}
                    longitude={lng}
                    latitude={lat}
                    onClick={() => handleSelectSite(s)}
                  >
                    <div
                      title={s.name}
                      style={{
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        background:
                          selectedSite?.id === s.id
                            ? "var(--color-accent-bright)"
                            : "var(--color-accent)",
                        border: "1px solid var(--color-bg-canvas)",
                        cursor: "pointer",
                      }}
                    />
                  </Marker>
                );
              } catch {
                return null;
              }
            })}

            {/* ── POI click popup ───────────────────────────────────────────── */}
            {poiPopup && (
              <Popup
                longitude={poiPopup.lng}
                latitude={poiPopup.lat}
                closeButton
                closeOnClick={false}
                onClose={() => setPoiPopup(null)}
                anchor="bottom"
                maxWidth="320px"
              >
                <div style={{
                  fontFamily: "'IBM Plex Sans', sans-serif",
                  fontSize: "12px",
                  color: "#1a1a1a",
                  lineHeight: 1.5,
                  padding: "2px 0",
                }}>
                  {/* Header — subcategory label + color dot */}
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px" }}>
                    <div style={{
                      width: "8px", height: "8px", borderRadius: "50%",
                      background: poiColor(poiPopup.category), flexShrink: 0,
                    }} />
                    <span
                      title={`${poiPopup.category} / ${poiPopup.subcategory}`}
                      style={{
                        fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.12em",
                        color: poiColor(poiPopup.category), fontWeight: 700,
                      }}
                    >
                      {poiPopup.subcategory.replace(/_/g, " ")}
                    </span>
                  </div>

                  {/* Name */}
                  {(poiPopup.name_en || poiPopup.name_ar) ? (
                    <div style={{ marginBottom: "8px" }}>
                      {poiPopup.name_en && (
                        <div style={{ fontWeight: 600, fontSize: "13px" }}>{poiPopup.name_en}</div>
                      )}
                      {poiPopup.name_ar && (
                        <div style={{ color: "#555", direction: "rtl", fontSize: "12px" }}>{poiPopup.name_ar}</div>
                      )}
                    </div>
                  ) : (
                    <div style={{ color: "#999", fontStyle: "italic", marginBottom: "8px", fontSize: "12px" }}>Unnamed</div>
                  )}

                  <div style={{ borderTop: "1px solid #e5e5e5", marginBottom: "8px" }} />

                  {/* Operator / Brand */}
                  {(poiPopup.operator || poiPopup.brand) && (
                    <div style={{ marginBottom: "4px" }}>
                      <span style={{ color: "#888", fontSize: "10px" }}>Operator: </span>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "11px" }}>
                        {poiPopup.operator && poiPopup.brand && poiPopup.operator !== poiPopup.brand
                          ? `${poiPopup.operator} / ${poiPopup.brand}`
                          : (poiPopup.operator ?? poiPopup.brand)}
                      </span>
                    </div>
                  )}

                  {/* Address */}
                  {poiPopup.address && (
                    <div style={{ marginBottom: "4px" }}>
                      <span style={{ color: "#888", fontSize: "10px" }}>Address: </span>
                      <span style={{ fontSize: "11px" }}>{poiPopup.address}</span>
                    </div>
                  )}

                  {/* Contact row */}
                  {(poiPopup.phone || poiPopup.website || poiPopup.opening_hours) && (
                    <div style={{ marginBottom: "4px", display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
                      {poiPopup.phone && (
                        <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "#444" }}>
                          {poiPopup.phone}
                        </span>
                      )}
                      {poiPopup.website && (
                        <a
                          href={poiPopup.website.startsWith("http") ? poiPopup.website : `https://${poiPopup.website}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ fontSize: "10px", color: "#C9922A", textDecoration: "none" }}
                        >
                          website ↗
                        </a>
                      )}
                      {poiPopup.opening_hours && (
                        <span style={{ fontSize: "10px", color: "#555" }}>
                          {poiPopup.opening_hours === "24/7" ? "Open 24/7" : `Hours: ${poiPopup.opening_hours}`}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Divider */}
                  {(poiPopup.footprint_area_sqm || poiPopup.building_levels || poiPopup.height_m || poiPopup.capacity) && (
                    <>
                      <div style={{ borderTop: "1px solid #e5e5e5", marginBottom: "8px", marginTop: "4px" }} />
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "4px" }}>
                        {poiPopup.footprint_area_sqm && (
                          <span style={{ fontSize: "11px" }}>
                            <span style={{ color: "#888", fontSize: "10px" }}>Footprint: </span>
                            <span style={{ fontVariantNumeric: "tabular-nums" }}>
                              {Math.round(poiPopup.footprint_area_sqm).toLocaleString()} m²
                            </span>
                          </span>
                        )}
                        {poiPopup.building_levels && (
                          <span style={{ fontSize: "11px" }}>
                            <span style={{ color: "#888", fontSize: "10px" }}>Levels: </span>
                            <span style={{ fontVariantNumeric: "tabular-nums" }}>{poiPopup.building_levels}</span>
                          </span>
                        )}
                        {poiPopup.height_m && (
                          <span style={{ fontSize: "11px" }}>
                            <span style={{ color: "#888", fontSize: "10px" }}>Height: </span>
                            <span style={{ fontVariantNumeric: "tabular-nums" }}>{poiPopup.height_m}m</span>
                          </span>
                        )}
                        {poiPopup.capacity && (
                          <span style={{ fontSize: "11px" }}>
                            <span style={{ color: "#888", fontSize: "10px" }}>Capacity: </span>
                            <span style={{ fontVariantNumeric: "tabular-nums" }}>{poiPopup.capacity.toLocaleString()}</span>
                          </span>
                        )}
                      </div>
                    </>
                  )}

                  {/* Footer */}
                  <div style={{ borderTop: "1px solid #e5e5e5", marginTop: "6px", paddingTop: "6px" }}>
                    <span style={{ fontSize: "9px", color: "#aaa" }}>
                      Source: OpenStreetMap
                      {poiPopup.last_seen_at && ` · verified ${new Date(poiPopup.last_seen_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}`}
                    </span>
                  </div>
                </div>
              </Popup>
            )}
          </Map>

          {/* Draw mode hint */}
          {drawMode && (
            <div style={{
              position: "absolute",
              top: "12px",
              left: "50%",
              transform: "translateX(-50%)",
              background: "rgba(20,19,16,0.9)",
              border: "1px solid var(--color-accent)",
              color: "var(--color-accent)",
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              letterSpacing: "0.1em",
              padding: "4px 12px",
              zIndex: 3,
              textTransform: "uppercase",
            }}>
              {drawVertices.length < 3
                ? `Click to add vertices (${drawVertices.length} so far, need 3+)`
                : "Double-click to close polygon"}
              {drawVertices.length > 0 && (
                <button
                  onClick={() => { setDrawVertices([]); }}
                  style={{ marginLeft: "10px", background: "none", border: "none", color: "var(--color-negative)", cursor: "pointer", fontSize: "9px", fontFamily: "var(--font-mono)" }}
                >
                  clear
                </button>
              )}
            </div>
          )}

          {/* Velocity hover tooltip */}
          {velocityTooltip && (
            <div
              style={{
                position: "absolute",
                left: velocityTooltip.x + 12,
                top: velocityTooltip.y - 10,
                background: "rgba(20,19,16,0.95)",
                border: "1px solid var(--color-border-default)",
                padding: "6px 10px",
                zIndex: 4,
                pointerEvents: "none",
                minWidth: "160px",
              }}
            >
              <div style={{ fontSize: "10px", color: "var(--color-text-primary)", marginBottom: "4px" }}>
                {lang === "ar" && velocityTooltip.districtAr
                  ? velocityTooltip.districtAr
                  : velocityTooltip.district}
              </div>
              <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", display: "flex", flexDirection: "column", gap: "2px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <span>Transactions</span>
                  <span style={{ fontVariantNumeric: "tabular-nums", color: "var(--color-text-secondary)" }}>
                    {velocityTooltip.txCount}
                  </span>
                </div>
                {velocityTooltip.pricePerSqm != null && (
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span>SAR/sqm</span>
                    <span style={{ fontVariantNumeric: "tabular-nums", color: "var(--color-text-secondary)" }}>
                      {velocityTooltip.pricePerSqm.toFixed(0)}
                    </span>
                  </div>
                )}
                {velocityTooltip.latestMonth && (
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span>Latest</span>
                    <span style={{ fontVariantNumeric: "tabular-nums", color: "var(--color-text-secondary)" }}>
                      {velocityTooltip.latestMonth}
                    </span>
                  </div>
                )}
                <div style={{ marginTop: "2px", color: "var(--color-text-tertiary)", fontStyle: "italic" }}>
                  {velocityWindow}d window · {velocityAssetClass || "all types"}
                </div>
              </div>
            </div>
          )}

          {/* Velocity legend (bottom-right, shown when velocity layer active) */}
          {toggles.velocity && (
            <div
              style={{
                position: "absolute",
                bottom: "40px",
                right: "12px",
                background: "rgba(20,19,16,0.88)",
                border: "1px solid var(--color-border-subtle)",
                padding: "8px 10px",
                zIndex: 2,
                minWidth: "160px",
              }}
            >
              <div style={{ fontSize: "9px", color: "var(--color-text-tertiary)", marginBottom: "6px", letterSpacing: "0.08em" }}>
                Transaction density · last {velocityWindow}d
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "4px", marginBottom: "3px" }}>
                {[0.05, 0.2, 0.4, 0.65, 0.85].map((opacity, i) => (
                  <div
                    key={i}
                    style={{
                      flex: 1,
                      height: "8px",
                      background: `rgba(201,146,42,${opacity})`,
                    }}
                  />
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "8px", color: "var(--color-text-tertiary)", fontVariantNumeric: "tabular-nums" }}>
                <span>0</span>
                <span>Low</span>
                <span>High</span>
              </div>
              {velocityRows.length === 0 && (
                <div style={{ marginTop: "4px", fontSize: "8px", color: "var(--color-accent)", fontStyle: "italic" }}>
                  No data — awaiting REGA Open Data
                </div>
              )}
            </div>
          )}

          {/* Layer toggle controls */}
          <LayerControls
            toggles={toggles}
            onChange={setToggle}
            poiState={poiState}
            onPoiSubcat={setPoiSubcat}
            onPoiCat={setPoiCat}
            drawMode={drawMode}
            onDrawMode={setDrawMode}
            velocityWindow={velocityWindow}
            onVelocityWindow={setVelocityWindow}
            velocityAssetClass={velocityAssetClass}
            onVelocityAssetClass={setVelocityAssetClass}
            isoProfile={isoProfile}
            onIsoProfile={setIsoProfile}
            isoError={isoError}
          />

          {/* POI legend (shown when POI layer is on) — only active categories */}
          {toggles.pois && (
            <div
              style={{
                position: "absolute",
                bottom: "12px",
                left: "12px",
                background: "rgba(20,19,16,0.88)",
                border: "1px solid var(--color-border-subtle)",
                padding: "8px 10px",
                zIndex: 2,
              }}
            >
              {(Object.entries(POI_CAT_COLORS) as [string, string][])
                .filter(([cat]) => catToggleState(cat, poiState) !== "none")
                .map(([cat, color]) => (
                <div
                  key={cat}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    marginBottom: "3px",
                  }}
                >
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: color,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ fontSize: "9px", color: "var(--color-text-tertiary)" }}>
                    {cat}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Evaluation panel (saved site, ad-hoc click, or empty state) */}
        {selectedSite || adHocGeom ? (
          <EvalPanel
            site={selectedSite}
            adHocGeom={adHocGeom}
            onClear={() => {
              setSelectedSite(null);
              setAdHocGeom(null);
              setMarkerCoords(null);
            }}
            onPoiHover={setHoveredPoiCat}
          />
        ) : (
          <div
            style={{
              width: "360px",
              flexShrink: 0,
              borderLeft: "1px solid var(--color-border-subtle)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "24px",
            }}
          >
            <div
              style={{
                fontSize: "11px",
                color: "var(--color-text-tertiary)",
                textAlign: "center",
                lineHeight: 1.5,
              }}
            >
              Click any point on the map to evaluate a site, or select a saved site from the left rail.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
