// Intelligence Feed — Polish-source ingestion stream

import { useState } from "react";

const sources = [
  { n: "Eurobuild CEE",         type: "Trade press",  cov: "Office, retail, capital",     lang: "EN/PL", count: 142, last: "04:18", auth: "AAA", note: "Strongest Warsaw office desk." },
  { n: "Property Forum",        type: "Trade press",  cov: "Office, residential",          lang: "EN/PL", count:  98, last: "05:42", auth: "AA",  note: "" },
  { n: "Money.pl",              type: "Mainstream",   cov: "Macro, regulatory",            lang: "PL",    count:  76, last: "06:01", auth: "A",   note: "" },
  { n: "Bankier",               type: "Mainstream",   cov: "Capital markets, REITs",       lang: "PL",    count:  64, last: "05:28", auth: "AA",  note: "" },
  { n: "Rzeczpospolita · NRC",  type: "Newspaper",    cov: "Capital, regulatory",          lang: "PL",    count:  48, last: "05:14", auth: "AAA", note: "Long-form analysis priority." },
  { n: "Puls Biznesu",          type: "Newspaper",    cov: "Corporate, M&A",               lang: "PL",    count:  41, last: "06:08", auth: "AA",  note: "" },
  { n: "Forbes Polska",         type: "Magazine",     cov: "Capital markets, profile",     lang: "PL",    count:  22, last: "yesterday", auth: "A", note: "" },
  { n: "Dziennik Gazeta Prawna",type: "Newspaper",    cov: "Regulatory, courts",           lang: "PL",    count:  38, last: "05:51", auth: "AAA", note: "MPZP & UOKiK rulings." },
  { n: "Sejm RP · druk",        type: "Government",   cov: "Legislation",                  lang: "PL",    count:  14, last: "yesterday", auth: "AAA", note: "Bill texts & reading status." },
  { n: "NBP",                   type: "Government",   cov: "Macro, MIR, FX fixings",       lang: "PL/EN", count:  28, last: "02:00", auth: "AAA", note: "" },
  { n: "GUS",                   type: "Government",   cov: "Demographics, completions",    lang: "PL/EN", count:  32, last: "yesterday", auth: "AAA", note: "" },
  { n: "MRiT · Jawność feed",   type: "Government",   cov: "Primary developer prices",     lang: "PL",    count: 412, last: "06:14", auth: "AAA", note: "Statutory feed · 15-min cadence." },
  { n: "WSE · GPW",             type: "Government",   cov: "Listed-RE quotes",             lang: "PL/EN", count:  54, last: "05:35", auth: "AAA", note: "15-min delayed." },
  { n: "JLL Poland · publishing",type:"Consultancy",  cov: "Office, capital, research",   lang: "EN/PL", count:  18, last: "yesterday", auth: "AA", note: "Quarterly & ad-hoc reports." },
  { n: "CBRE Poland · publishing",type:"Consultancy", cov: "Office, logistics, retail",   lang: "EN/PL", count:  16, last: "yesterday", auth: "AA", note: "" },
  { n: "Internal · WSRE field", type: "Proprietary",  cov: "Broker, deal whisper",         lang: "EN",    count:  26, last: "04:42", auth: "AA",  note: "Manually verified." },
];

const facts = [
  { ts: "06:14", src: "MRiT · Jawność feed",      t: "transaction", txt: "Echo Investment repriced 8 units in Stacja Wola etap III (+2.34% to PLN 21,900/m²).",               tags: ["Echo Investment","Wola","Primary"],          conf: 5 },
  { ts: "06:08", src: "Eurobuild CEE",             t: "transaction", txt: "Allianz Real Estate completed Generation Park Y acquisition · €119.1m · 5.85% yield.",              tags: ["Allianz","Skanska","Wola","Capital markets"], conf: 5 },
  { ts: "06:02", src: "NBP",                       t: "sentiment",   txt: "NBP daily EUR/PLN fixing 4.2840 (+0.04% DoD).",                                                     tags: ["FX","Macro"],                                conf: 5 },
  { ts: "05:51", src: "Dziennik Gazeta Prawna",    t: "sentiment",   txt: "WSA Warsaw decision on Czyste-Towarowa MPZP appeals to be published 18 Apr.",                      tags: ["MPZP","Wola","Regulatory"],                  conf: 4 },
  { ts: "05:42", src: "Property Forum",            t: "listing",     txt: "Skanska Property lists Studio B floors 8–12 (4,800 sqm) at €25.50/sqm/mo asking.",                  tags: ["Skanska","Wola","Office"],                   conf: 5 },
  { ts: "05:35", src: "GPW",                       t: "sentiment",   txt: "GTC opens at PLN 7.84 (+0.51%) on volume 142k shares.",                                             tags: ["GTC","Listed RE"],                           conf: 5 },
  { ts: "05:28", src: "Bankier",                   t: "sentiment",   txt: "PFA-Norway press release confirms Forest Tower closing on Friday.",                                   tags: ["PFA","Wola","Capital markets"],              conf: 5 },
  { ts: "05:14", src: "Rzeczpospolita · NRC",      t: "sentiment",   txt: "FINN bill amendments tabled overnight — distribution mandate raised from 85% to 90%.",              tags: ["FINN","REIT","Regulatory"],                  conf: 4 },
  { ts: "04:42", src: "Internal · WSRE field",     t: "transaction", txt: "Broker indicates Empark Mokotów Phase II quietly to market with PineBridge BE — guide €92m at 7.40%.", tags: ["Mokotów","PineBridge","Capital markets"],conf: 3 },
  { ts: "04:18", src: "Eurobuild CEE",             t: "sentiment",   txt: "Citi BPO confirms V.Offices renewal + 3,000 sqm expansion (effective 1 May 2026).",                 tags: ["Citi","Mokotów","Office demand"],             conf: 5 },
  { ts: "03:55", src: "JLL Poland · publishing",   t: "sentiment",   txt: "JLL Q1 office report: prime CBD rent EUR 27.00/sqm/mo unchanged QoQ; vacancy 11.2% (-30 bps).",    tags: ["Office","CBD","JLL"],                        conf: 5 },
  { ts: "02:12", src: "MRiT · Jawność feed",       t: "transaction", txt: "Marvipol repriced 6 units in Unisono Wola (+2.23% to PLN 22,900/m²).",                              tags: ["Marvipol","Wola","Primary"],                 conf: 5 },
  { ts: "yesterday", src: "Sejm RP · druk",        t: "sentiment",   txt: "FINN bill (druk 412) referred to second reading.",                                                  tags: ["FINN","Regulatory"],                         conf: 5 },
  { ts: "yesterday", src: "GUS",                   t: "sentiment",   txt: "Q1 office completions Warsaw: 142,000 sqm (CEE-leading).",                                          tags: ["Macro","Pipeline"],                          conf: 5 },
];

function ConfDots({ n }: { n: number }) {
  return (
    <div style={{ display: "inline-flex", gap: 2 }}>
      {[1, 2, 3, 4, 5].map(i => (
        <div key={i} style={{
          width: 6, height: 6, borderRadius: "50%",
          background: i <= n ? "var(--brand-navy)" : "var(--border)",
        }} />
      ))}
    </div>
  );
}

export function IntelligencePage() {
  const [activeType, setActiveType] = useState("all");
  const [activeSrc, setActiveSrc] = useState<string | null>(null);

  const filtered = facts.filter(f => {
    if (activeType !== "all" && f.t !== activeType) return false;
    if (activeSrc && f.src !== activeSrc) return false;
    return true;
  });

  const totalCount = sources.reduce((a, s) => a + s.count, 0);

  return (
    <div style={{ display: "flex", height: "calc(100vh - 100px)", overflow: "hidden" }}>
      {/* Left rail — sources */}
      <aside style={{ width: 340, background: "#fff", borderRight: "1px solid var(--border)", overflowY: "auto", flexShrink: 0 }}>
        <div style={{ padding: "20px 22px 14px", borderBottom: "1px solid var(--divider)" }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Sources</h2>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4 }}>
            16 active feeds · {totalCount.toLocaleString()} facts last 7d
          </div>
        </div>
        <div>
          <button
            onClick={() => setActiveSrc(null)}
            style={{
              width: "100%", textAlign: "left", padding: "10px 22px",
              border: "none",
              background: !activeSrc ? "var(--bg-selected)" : "transparent",
              cursor: "pointer", fontFamily: "inherit", fontSize: 13,
              color: !activeSrc ? "var(--brand-navy)" : "var(--text-primary)",
              borderBottom: "1px solid var(--divider)",
              boxShadow: !activeSrc ? "inset 2px 0 0 var(--brand-navy)" : "none",
              fontWeight: !activeSrc ? 500 : 400,
            }}
          >
            All sources <span className="tnum" style={{ float: "right", color: "var(--text-secondary)" }}>{totalCount}</span>
          </button>
          {sources.map(s => (
            <button
              key={s.n}
              onClick={() => setActiveSrc(s.n === activeSrc ? null : s.n)}
              style={{
                width: "100%", textAlign: "left", padding: "10px 22px",
                border: "none",
                background: activeSrc === s.n ? "var(--bg-selected)" : "transparent",
                cursor: "pointer", fontFamily: "inherit",
                borderBottom: "1px solid var(--divider)",
                boxShadow: activeSrc === s.n ? "inset 2px 0 0 var(--brand-navy)" : "none",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: activeSrc === s.n ? 500 : 400 }}>{s.n}</div>
                <div className="tnum" style={{ fontSize: 11, color: "var(--text-secondary)" }}>{s.count}</div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{s.type} · {s.lang}</div>
                <div className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{s.last}</div>
              </div>
              {s.note && <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 3, fontStyle: "italic" }}>{s.note}</div>}
              <span style={{
                display: "inline-block", marginTop: 4,
                fontSize: 10, padding: "1px 5px", border: "1px solid",
                borderColor: s.auth === "AAA" ? "var(--brand-navy)" : s.auth === "AA" ? "var(--text-secondary)" : "var(--text-tertiary)",
                color: s.auth === "AAA" ? "var(--brand-navy)" : s.auth === "AA" ? "var(--text-secondary)" : "var(--text-tertiary)",
              }}>{s.auth}</span>
            </button>
          ))}
        </div>
        {/* Methodology footer */}
        <div style={{ padding: "16px 22px 20px", fontSize: 11, color: "var(--text-secondary)", borderTop: "1px solid var(--border)" }}>
          <div className="ws-upper" style={{ marginBottom: 6 }}>Methodology</div>
          <div style={{ lineHeight: 1.55, marginBottom: 12 }}>
            Facts ingested every 60s. Polish sources translated to EN by domain-tuned model; original PL preserved on hover. Each fact tagged for entity, district, and asset class via NER. Confidence rests on source authority × corroboration count.
          </div>
          <div className="ws-upper" style={{ marginBottom: 6 }}>Authority</div>
          <div style={{ lineHeight: 1.6 }}>
            <strong>AAA</strong> — government statutory / regulated<br />
            <strong>AA</strong> — specialist trade press + consultancy<br />
            <strong>A</strong> — mainstream business press<br />
            <strong>BBB</strong> — social / unverified
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="ws-upper" style={{ marginBottom: 6 }}>Coverage</div>
            <div style={{ lineHeight: 1.55 }}>
              No scraping of residential listing portals (OtoDom, Domiporta). Primary residential prices sourced exclusively from the MRiT Jawność statutory feed.
            </div>
          </div>
        </div>
      </aside>

      {/* Main feed */}
      <div style={{ flex: 1, overflowY: "auto", background: "#fff" }}>
        {/* Filter bar */}
        <div style={{ padding: "14px 24px", borderBottom: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center", position: "sticky", top: 0, background: "#fff", zIndex: 5 }}>
          <span style={{ fontSize: 11, color: "var(--text-secondary)", marginRight: 4 }}>Type:</span>
          {["all", "transaction", "listing", "sentiment", "regulatory"].map(t => (
            <span key={t} className={"chip" + (activeType === t ? " active" : "")} onClick={() => setActiveType(t)} style={{ fontSize: 11 }}>
              {t === "all" ? "All" : t.charAt(0).toUpperCase() + t.slice(1)}
            </span>
          ))}
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-tertiary)" }}>
            {filtered.length} facts
            {activeSrc && <> · <strong>{activeSrc}</strong></>}
          </span>
        </div>

        {/* Facts */}
        <div style={{ padding: "0 24px" }}>
          {filtered.map((f, i) => (
            <div key={i} style={{ padding: "16px 0", borderBottom: "1px solid var(--divider)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)", minWidth: 60 }}>{f.ts}</span>
                <span className={"type-pill " + f.t}>{f.t}</span>
                <span style={{ fontSize: 11, color: "var(--text-secondary)", flex: 1 }}>{f.src}</span>
                <ConfDots n={f.conf} />
              </div>
              <div style={{ fontSize: 13.5, color: "var(--text-primary)", lineHeight: 1.5 }}>{f.txt}</div>
              <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                {f.tags.map((tag, ti) => (
                  <span key={ti} style={{ fontSize: 10, padding: "2px 6px", background: "var(--bg-wash)", color: "var(--text-secondary)" }}>{tag}</span>
                ))}
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: "48px 0", textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>
              No facts match the selected filters.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
