# WSRE Intelligence — Warsaw

> Real estate market intelligence for Poland, built on the world's most transparent primary-market apartment pricing feed.

![WSRE Intelligence Workbench — ul. Towarowa 28 demo plot with full 9-section evaluation](docs/workbench-demo.png)

## What This Is

WSRE Intelligence is an agentic real estate intelligence platform for the Warsaw market. It ingests Poland's statutory *Jawność cen mieszkań* primary-market pricing feed, queries live Warsaw municipal zoning data, synthesises weekly research briefs via Claude Opus, and provides Warsaw-area developers, foreign capital, and asset managers with a unified workbench for plot-level underwriting decisions.

## The Wedge

In July 2025 Poland passed *Ustawa o jawności cen mieszkań* — a transparency law requiring every primary-market real estate developer to publish daily, machine-readable XML files of every apartment price, every price change, and every reservation status. Approximately 1,000 developers nationally, 200+ in Warsaw alone, all publishing daily, by law. The data is free, CC0-licensed, machine-readable. And it's nearly invisible — schema variations across developers, all in Polish, the government portal essentially unusable.

WSRE Intelligence is the canonical interpretive layer over this data. Foreign capital cannot access it without a Polish team. Polish developers cannot measure their competitors at this granularity without a dedicated analyst team. The platform productises both use cases.

## Project Origin and Fork Disclosure

**This Warsaw platform is a fork of an earlier Saudi Arabia version of the same architecture, also built by Karol Blasinski for CS 153.**

The Saudi version — *WSRE Intelligence — Riyadh Industrial* — focused on industrial real estate in the Gulf. I pivoted to Warsaw mid-course after identifying that the Polish data landscape was significantly richer than the Saudi equivalent. Specifically:

- The *Jawność cen mieszkań* feed has no Saudi equivalent — Poland is one of the only major markets globally with mandatory daily primary-market price publication
- Warsaw municipal GIS (BGiK) exposes the full enacted zoning catalogue as a documented public API
- Polish trade press (Eurobuild CEE, inwestycje.pl) provides high-density, English+Polish coverage that the Saudi equivalent lacks
- The pending FINN bill (Polish REIT-equivalent legislation) creates a 12–24 month first-mover window before international REIT vehicles enter the market

The pivot to Warsaw allowed the platform to demonstrate substantially more sophisticated data integration than the Saudi version permitted.

Both projects represent my own continuous engineering work. The Warsaw version inherits approximately 70% of the architecture from the Saudi version (API patterns, brief synthesis pipeline, news ingestion framework, frontend component library, Postgres schema patterns), with the remaining 30% representing Warsaw-specific original work. See [AI_DISCLOSURE.md](./AI_DISCLOSURE.md) for full disclosure on what was human-driven vs. AI-assisted.

**Warsaw-specific original work includes:**

- Complete *Jawność cen mieszkań* ingestion pipeline (16,175 datasets discovered, 85,130 dwelling rows in Postgres across 1,351 developers)
- Warsaw BGiK WMS integration with custom MapLibre raster tile protocol for live MPZP zoning overlays
- Polish-language news scraping (Eurobuild CEE + inwestycje.pl) with Haiku-triage + Sonnet-extraction pipeline producing 456 typed facts across 8 fact tables
- Plot Evaluation Workbench with 9 distinct sections (zoning, comps, exit pricing, competing supply, demographics, infrastructure, regulatory, intelligence, underwriting)
- Section I underwriting model with function-aware build cost resolution and blended exit pricing for U(MW) mixed-use plots
- POI ingestion from OpenStreetMap Overpass API across 6 categories (5,804 POIs total)
- PostGIS spatial joins for canonical Warsaw 18-dzielnica district resolution
- Polish/English language toggle with 30-key translation dictionary
- Compare mode for side-by-side plot evaluation
- Warsaw-specific brief synthesis prompt with Polish RE editorial voice

## Quick Facts

| Metric | Value |
|--------|-------|
| Dwelling rows in Postgres | 85,130 |
| *Jawność* datasets discovered | 16,175 |
| Developers with data | 1,351 |
| Warsaw investments tracked | 1,301 |
| Warsaw districts with pricing data | 15 of 18 |
| POIs (schools, healthcare, parks, transit) | 5,804 |
| Typed RE facts across 8 fact tables | 456 |
| News articles processed by AI pipeline | 134 |
| Backend migrations | 23 |
| Weekly brief cost (Claude Opus) | ~$0.65 |
| Total build time, solo | 6 weeks |

## Live Demo

📹 [Watch the demo](https://drive.google.com/file/d/103fP8VHmNxfK1nRUS0NQSygvpk2fLvR8/view?usp=sharing)

For pilot conversations and detailed walkthroughs: kblasins@stanford.edu

## Project Submission Supplement

> **Note on this section:** The CS 153 final project video requirements were extended from 3 minutes to under 10 minutes after submission opened. Rather than expand the demo video, this section addresses the four required submission questions (Q1–Q4) and the five rubric criteria (Problem & Insight, Execution & Technical Work, Evaluation & Evidence, Communication & Presentation, Process & Integrity) in written form. Per course staff guidance, this content counts toward rubric evaluation alongside the 3-minute demo video.

### Q1: Why did I build what I did?

**The bottleneck.**

Polish residential real estate has a structural information asymmetry. Mid-market developers, foreign capital evaluating Warsaw entries, and Polish family offices all face the same problem: the most transparent primary-market apartment pricing data in Europe sits unused because nobody has built the interpretive layer.

In July 2025, Poland passed Ustawa o jawności cen mieszkań (Dz.U. 2023 poz. 1114), a transparency law requiring every primary-market real estate developer in Poland to publish daily, machine-readable XML files containing every apartment price, every price change, every reservation status. About 1,000 developers nationally, over 200 in Warsaw alone, all publishing daily, by law, free, CC0-licensed.

The data is genuinely public. It is also genuinely unusable: heterogeneous XML schemas across developers (some publish CSV, some XLSX, some JSON), all in Polish, the government portal at dane.gov.pl has no aggregation or search. Foreign capital cannot access this data without a Polish team. Polish developers cannot measure their competitors at this granularity without five full-time analysts.

Adjacent to this primary-market wedge, three more Polish data infrastructure changes opened in parallel:
- The Warsaw municipal BGiK service exposed the full enacted zoning catalog as a documented public API (although geo-restricted to Polish IPs)
- The pending FINN bill (Polish REIT-equivalent legislation) is creating a 12–24 month first-mover window before international REIT vehicles enter the market
- Polish trade press (Eurobuild CEE, inwestycje.pl) provides high-density bilingual coverage that no aggregator surfaces

**The inspiration.**

I am moving into real estate professionally after graduation, and through prior research and industry exposure I have developed a working familiarity with both the CEE and Gulf real estate markets. The Polish data wedge is not a thought experiment — it is the gap I have personally felt while doing underwriting and market analysis work, and a gap I believe is currently invisible to the broader market.

I started this course building a Saudi Arabia version of the same architecture, focused on industrial real estate in the Gulf. When I identified mid-course that the Polish data landscape was substantially richer — particularly the Jawność feed which has no Saudi equivalent — I pivoted to Warsaw. The Warsaw version inherits the architecture from the Saudi work, applied to a more interesting data substrate.

### Q2: How exactly does the product work?

This is an **Application / Product** with **Automation / Agent Systems** components. It is a Domain-Specific tool for Polish real estate.

**Product architecture.**

The platform is a four-layer stack:

1. **Ingestion layer** — three independent pipelines:
   - Jawność cen mieszkań: discovers developer datasets via dane.gov.pl CKAN API, fetches XML/CSV/XLSX/JSON feeds, normalizes through a schema-tolerant parser, upserts into PostgreSQL
   - OpenStreetMap POIs: Overpass API queries for schools, healthcare, parks, metro, tram, rail (5,804 POIs in 6 categories)
   - Warsaw BGiK WMS: custom MapLibre raster protocol that converts z/x/y tiles to EPSG:4326 GetMap requests for live zoning overlays
   - Polish news: scrapers for Eurobuild CEE and inwestycje.pl with rate limiting and User-Agent identification

2. **AI processing layer** — three-tier agentic pipeline for fact extraction:
   - **Claude Haiku 4.5** scores scraped articles 0–1 for Polish/Warsaw RE relevance (~$0.02 per article)
   - **Claude Sonnet 4.6** extracts structured facts from triage-passed articles into 8 typed fact tables: supply_events, capital_markets_events, regulatory_events, macro_signals, tenant_signals, demand_signals, market_commentary, infrastructure_events (~$0.06 per article)
   - **Claude Opus 4.6** synthesizes the weekly research brief from 313 Warsaw-filtered facts (~$0.65 per brief)

3. **Storage layer** — PostgreSQL with PostGIS extension:
   - 85,130 dwelling rows in `primary_pricing`
   - 1,591 ingested developer datasets in `jawnosc_developers` (mapped to firms via `developer_firms`)
   - 5,804 POIs in `warsaw_pois` with PostGIS spatial indexes
   - Warsaw dzielnica boundaries in `warsaw_districts` (multipolygon geometries from OSM admin_level=9)
   - Plot-level seed data in `plot_zoning_seed`, `plot_land_comps_seed`, `plot_demographics_seed`, `plot_infrastructure_seed`, `plot_regulatory_seed`
   - News articles and 456 extracted facts in `news_articles` and 8 fact tables
   - Generated briefs in `briefs` with full structured JSON

4. **Frontend** — React + TypeScript + Tailwind + MapLibre, served via Vite. Eight pages: Workbench, Briefs, Markets (Commercial, Primary Residential), Submarkets, Intelligence Feed, Admin, plus authentication. PostgreSQL spatial queries surface as GeoJSON via FastAPI endpoints.

**The agentic Jawność pipeline.**

The novel automation here is end-to-end: scrape → triage → extract → synthesize. A user pulls up the Briefs page and reads a research brief. Behind that brief: 134 articles scraped from Polish trade press in the prior week, 46 passed Haiku triage, 456 facts extracted via Sonnet, 313 Warsaw-geo-filtered, Opus synthesized them into editorial-grade copy with verbatim Polish source citations. Total automation cost per brief: ~$0.65. The same brief from a human research analyst would cost $500–2,000.

**Deployment.**

Current state: runs locally on a developer Mac (with NordVPN to Poland for live Warsaw WMS access). PostgreSQL + Python backend + Vite frontend. Production deployment planned to Cloudflare Workers from a Warsaw edge node (Cloudflare for Startups credits applied for) to eliminate the VPN dependency for Warsaw municipal WMS calls.

### Q3: Potential use cases of the product?

Three distinct customer personas:

**Persona A — Polish residential developers underwriting land acquisitions.**

A mid-market Warsaw developer evaluating a 1,500m² plot needs zoning, comparable transactions, exit pricing, competing supply, demographics, infrastructure proximity, regulatory exposure, and an underwriting calculation. Today this takes 3–5 days of manual research across 6+ disconnected systems. The Plot Evaluation Workbench compresses this to under 30 seconds. Estimated economic value: meaningful saved analyst time, plus better-informed pricing on the bid itself.

**Persona B — Foreign capital evaluating Warsaw entries.**

A Frankfurt or London-based fund manager evaluating CEE diversification cannot read Polish, cannot interpret Polish zoning law, and cannot access the Polish-language data infrastructure. The platform provides English-language synthesis of all of the above, plus methodological transparency that supports diligence workflows. Estimated value: avoids the cost of staffing a Warsaw analyst team for early-stage market exploration.

**Persona C — Asset managers tracking pricing power across Warsaw.**

A Warsaw-based or CEE-focused asset manager managing existing Warsaw residential or mixed-use exposure needs real-time signals on the markets where they have positions. Daily updates on developer pricing moves, weekly research synthesis, district-level competitive dynamics. The Jawność-driven Recent Price Changes feed is a leading indicator of demand stress and absorption velocity that no incumbent (JLL, CBRE, Cushman & Wakefield Poland) currently publishes at this granularity. Estimated value: improved entry and exit timing on existing positions.

**Societal impact.**

The Jawność law was designed to reduce information asymmetry in the Polish primary-market — to give buyers, developers, and policymakers equal access to market data. In practice, the data remains practically inaccessible to most stakeholders due to the technical barriers described above. The platform realizes the public interest the legislation was designed to enable: foreign capital flows into Polish real estate more efficiently, Polish developers compete on pricing rather than information opacity, and Polish residential market dynamics become legible to policymakers, journalists, and academic researchers. The platform's institutional pilot tier (€399/seat/month) is intended to cross-subsidize a planned public-facing observatory that publishes aggregate Polish market trends openly.

### Q4: What more would I add?

In four categories, in approximate priority order:

**Data layer expansion (next 8 weeks):**
- Real RCN (Rejestr Cen Nieruchomości) ingestion replacing the current hand-seeded Section B land comparable transactions, via the Warsaw BGiK MSCT_GN_* and RCIWN_GRUNTY_* layers
- GUS BDL ingestion for real demographic data per dzielnica (currently hand-seeded for the demo plot only)
- Vector-level MPZP ingestion (currently overlay-only via WMS; need plan-by-plan vector polygons in PostgreSQL for spatial queries)
- Notarial deed transaction registry — the canonical Polish secondary-market data source not currently in pipeline
- News source expansion: Rzeczpospolita Nieruchomości, Puls Biznesu, Bankier, Property Forum

**Product depth (months 2–4):**
- "Pricing Power Index" — a real-time index per developer, per investment, per dzielnica measuring how aggressively pricing is moving relative to absorption velocity. This is a number nobody else publishes because nobody else has the Jawność feed integration. Becomes the platform's signature metric.
- "Developer Playbooks" — after 6+ months of Jawność history, the platform publishes characterizations of each major developer's pricing strategy: tier-and-hold pricing, aggressive discrimination, stocking-clearance signals. Product no consultant offers because consultants serve developers and cannot expose their pricing playbook publicly.
- WZ Precedent Search — for every plot subject to case-by-case "decyzja o warunkach zabudowy" rather than enacted MPZP, search what has been granted within 500m. Addresses a uniquely Polish risk dimension.
- FINN/REIT readiness tracker — once the FINN bill passes, the first 18 months will see vehicle launches, listed-equity-to-REIT conversions, and capital reallocation. A platform with this tracked from before passage has authority on day one of the new regime.

**Productionization (months 1–2):**
- Cloudflare Workers deployment from Warsaw edge — eliminates VPN dependency, makes platform accessible to non-Polish viewers including the foreign capital persona
- Polish-language coverage extension — currently translation toggle covers ~30 keys (nav + Workbench right rail); full coverage needed for brief body, news facts, admin interface
- Editable Section I underwriting inputs with live recompute — currently read-only; need to wire user-modifiable build cost, IRR target, financing assumptions
- Plot search/filter UI — currently demo-plot-driven; need to support arbitrary plot selection from the map

**Validation and customer development (months 1–3):**
- 5 customer interviews each with Polish residential developers, foreign capital allocators, and Warsaw-area family offices — explicitly deferred until post-CS153
- Comparative benchmarking against JLL Poland, CBRE Poland, Cushman & Wakefield Poland published research
- Pilot rollout to early-access partners
- Pricing validation — €399/seat/month current hypothesis; institutional tier pricing TBD via pilot conversations

### Rubric Cross-Reference

For graders evaluating against the published rubric:

**Problem & Insight (3 pts):**
- Meaningful problem: Polish RE data infrastructure exists but is unusable; foreign capital and Polish developers both blocked
- Compelling motivation: 12–24 month first-mover window before incumbents
- Original approach: agentic synthesis pipeline over a uniquely Polish statutory data feed
- See: Q1 above, plus README "The Wedge" section

**Execution & Technical Work (5 pts):**
- 85,130 dwelling rows ingested from heterogeneous Polish XML schemas
- PostGIS spatial joins, multi-format parser (CSV/XLSX/JSON), agentic three-tier pipeline (Haiku → Sonnet → Opus)
- Real Warsaw municipal WMS integration with custom MapLibre protocol
- Three end-to-end working capabilities (live data, plot evaluation, weekly brief) with real data
- See: Q2 above, plus [ARCHITECTURE.md](./ARCHITECTURE.md)

**Evaluation & Evidence (3 pts):**
- Three specific dwellings verified against developer public websites
- Numerical integrity tests against publicly reported Warsaw averages
- Two anchor claims in the weekly brief traced to verbatim Polish-language source citations
- Methodology footer in brief discloses 4 specific data coverage gaps transparently
- Five documented failure analyses with root cause and fix
- Explicitly named limitations: no customer interviews, no comparative benchmarks, no expert validation, single-user platform
- See: [LIMITATIONS.md](./LIMITATIONS.md), particularly the Failure Analysis section

**Communication & Presentation (2 pts):**
- 3-minute demo video covering the four submission questions at high level
- This README section providing depth on rubric criteria
- Five-document documentation structure: README, AI_DISCLOSURE, ARCHITECTURE, CONTRIBUTING, LIMITATIONS
- Reproducible locally per CONTRIBUTING.md
- See: this section, plus [CONTRIBUTING.md](./CONTRIBUTING.md)

**Process, Integrity & Disclosure (2 pts):**
- AI usage thoroughly disclosed per [AI_DISCLOSURE.md](./AI_DISCLOSURE.md): Claude Code for development, three-tier Claude models for production, Claude in chat for strategic work
- Saudi Arabia fork disclosed prominently in this README and AI_DISCLOSURE — both versions are my own continuous engineering work
- Public repository with full commit history visible at github.com/kblasins/wsre-intelligence
- Major decisions and limitations documented openly
- See: [AI_DISCLOSURE.md](./AI_DISCLOSURE.md)

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for system architecture, data flow diagram, and component overview.

## Setup & Reproducibility

See [CONTRIBUTING.md](./CONTRIBUTING.md) for local setup instructions. Full reproduction of WMS layers requires a Polish IP address or VPN; the Plot Evaluation demo works without it.

## AI Tool Usage Disclosure

This project was developed with extensive use of Claude (Anthropic) tools. Full disclosure in [AI_DISCLOSURE.md](./AI_DISCLOSURE.md).

## Limitations & Known Issues

See [LIMITATIONS.md](./LIMITATIONS.md) for full discussion of data coverage gaps, technical debt, deployment constraints, and documented failure analysis.

## License

MIT License. See [LICENSE](./LICENSE).

## Author

Karol Blasinski
Stanford GSB MBA 2026
CS 153 — Frontier Systems, Spring 2026
Built for the One-Person Frontier Lab project

For pilot conversations and project inquiries: kblasins@stanford.edu
