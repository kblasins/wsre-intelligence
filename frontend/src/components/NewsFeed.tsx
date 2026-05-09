import { useEffect, useRef, useState } from "react";
import { useNews, useNewsVolume } from "../hooks/useMarketData";
import { formatDate } from "../lib/format";
import type { NewsArticle } from "../types/api";
import { NewsArticleModal } from "./NewsArticleModal";
import { NewsSourceDonut } from "./charts/NewsSourceDonut";
import { NewsVolumeChart } from "./charts/NewsVolumeChart";

const SOURCE_LABELS: Record<string, string> = {
  argaam_en:     "Argaam EN",
  argaam_ar:     "Argaam AR",
  modon:         "MODON",
  knight_frank:  "Knight Frank",
  saudi_gazette: "Saudi Gazette",
  arab_news:     "Arab News",
};

const ALL_SOURCES = Object.keys(SOURCE_LABELS);

export function NewsFeed() {
  const { data: volumeData } = useNewsVolume(12);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [activeSource, setActiveSource] = useState<string | null>(null);
  const [minRelevance, setMinRelevance] = useState(0.5);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setDebouncedQ(searchQuery), 350);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [searchQuery]);

  const { data: articles, isLoading, error } = useNews(100, debouncedQ || undefined);

  const filtered = articles?.filter(a =>
    (!activeSource || a.source === activeSource) &&
    (a.relevance_score == null || a.relevance_score >= minRelevance)
  ) ?? [];

  const hasFilters = !!(debouncedQ || searchQuery || activeSource || minRelevance !== 0.5);

  return (
    <section style={{ marginTop: "32px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid var(--border)",
      }}>
        <h3 className="ws-sub-h">Intelligence Feed</h3>
        {articles && articles.length > 0 && (
          <span className="ws-small" style={{ fontVariantNumeric: "tabular-nums" }}>
            {filtered.length}{filtered.length !== articles.length ? ` / ${articles.length}` : ""} articles
          </span>
        )}
      </div>

      {/* Filter bar */}
      {articles && articles.length > 0 && (
        <div style={{
          display: "flex", alignItems: "center", gap: "8px",
          marginBottom: "12px", flexWrap: "wrap",
        }}>
          <input
            type="text"
            placeholder="Search…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              background: "var(--bg-surface)", border: "1px solid var(--border)",
              color: "var(--text-primary)", fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "12px", padding: "5px 10px", outline: "none",
              width: "180px", borderRadius: "3px",
            }}
          />

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span className="ws-small">rel ≥ {minRelevance.toFixed(1)}</span>
            <input
              type="range" min={0} max={1} step={0.1} value={minRelevance}
              onChange={e => setMinRelevance(parseFloat(e.target.value))}
              style={{ width: "72px", accentColor: "var(--brand-navy)", cursor: "pointer" }}
            />
          </div>

          <div style={{ width: "1px", height: "20px", background: "var(--border)" }} />

          {ALL_SOURCES.map(src => (
            <button
              key={src}
              className={`chip${activeSource === src ? " active" : ""}`}
              onClick={() => setActiveSource(activeSource === src ? null : src)}
            >
              {SOURCE_LABELS[src]}
            </button>
          ))}

          {hasFilters && (
            <button
              onClick={() => { setSearchQuery(""); setDebouncedQ(""); setActiveSource(null); setMinRelevance(0.5); }}
              className="btn ghost"
              style={{ fontSize: "12px" }}
            >
              Clear
            </button>
          )}
        </div>
      )}

      {isLoading && <div className="load-bar"><div className="load-bar-inner" /></div>}

      {error && <p className="ws-meta">Could not load news.</p>}

      {!isLoading && !error && articles?.length === 0 && !debouncedQ && !activeSource && (
        <div className="empty-state">
          <p style={{ marginBottom: "8px", fontWeight: 500 }}>No articles yet.</p>
          <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", color: "var(--brand-navy)" }}>
            SCRAPER_LIVE_MODE=true
          </code>
        </div>
      )}

      {!isLoading && !error && filtered.length === 0 && ((articles?.length ?? 0) > 0 || activeSource) && (
        <div className="empty-state">No articles match the current filter.</div>
      )}

      {filtered.length > 0 && (
        <div className="ws-card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="ws-table">
            <thead>
              <tr>
                <th style={{ width: "48px" }}>Score</th>
                <th>Title &amp; Signal</th>
                <th style={{ width: "120px" }}>Source</th>
                <th style={{ width: "100px" }}>Published</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((article, i) => (
                <ArticleRow key={article.id} article={article} index={i} onClick={() => setSelectedId(article.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {volumeData && volumeData.length > 0 && <NewsVolumeChart data={volumeData} />}
      <NewsSourceDonut />

      {selectedId !== null && (
        <NewsArticleModal articleId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </section>
  );
}

function ArticleRow({ article, index, onClick }: { article: NewsArticle; index: number; onClick: () => void }) {
  const title = article.title_en ?? article.title_ar ?? "(no title)";
  const sourceLabel = SOURCE_LABELS[article.source] ?? article.source;
  const signal = typeof article.structured_facts?.market_signal === "string"
    ? article.structured_facts.market_signal as string
    : null;

  const score = article.relevance_score;
  const scoreColor = score == null ? "var(--text-tertiary)" : score >= 0.7 ? "var(--up)" : score >= 0.4 ? "var(--warn)" : "var(--text-tertiary)";

  return (
    <tr
      className="fade-up"
      style={{ animationDelay: `${index * 30}ms`, cursor: "pointer" }}
      onClick={onClick}
    >
      {/* Score */}
      <td className="num mono" style={{ color: scoreColor, fontWeight: 500 }}>
        {score != null ? Math.round(score * 100) : "—"}
      </td>

      {/* Title + signal */}
      <td>
        <div style={{ fontSize: "13px", color: "var(--text-primary)", lineHeight: 1.4, marginBottom: signal ? "4px" : 0 }}>
          {article.url ? (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--text-primary)", textDecoration: "none" }}
              onClick={e => e.stopPropagation()}
              onMouseEnter={e => { (e.target as HTMLAnchorElement).style.color = "var(--brand-navy)"; }}
              onMouseLeave={e => { (e.target as HTMLAnchorElement).style.color = "var(--text-primary)"; }}
            >
              {title}
            </a>
          ) : title}
        </div>
        {signal && (
          <div style={{ fontSize: "12px", color: "var(--text-secondary)", fontStyle: "italic", lineHeight: 1.4 }}>
            {signal}
          </div>
        )}
      </td>

      {/* Source */}
      <td>
        <span className="type-pill">{sourceLabel}</span>
      </td>

      {/* Date */}
      <td style={{ fontSize: "12px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
        {article.published_at ? formatDate(article.published_at) : "—"}
      </td>
    </tr>
  );
}
