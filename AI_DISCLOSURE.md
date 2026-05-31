# AI Tool Usage Disclosure

This project was developed with extensive use of AI tools throughout. Per the CS 153 AI policy and the project rubric's Process, Integrity & Disclosure criterion, this document provides a thorough accounting of where and how AI was used.

## Summary

Claude (Anthropic) was used extensively in three distinct roles:
1. **Code generation and engineering** via Claude Code (CLI agent)
2. **Production data processing** within the platform itself at runtime
3. **Strategic, product, and editorial work** via Claude in chat

---

## 1. Claude Code (development tooling)

Claude Code (Anthropic's CLI coding agent, powered by Claude Sonnet 4.6) was the **primary engineering tool** for this project. Across approximately 6 weeks of development:

- All backend code (Python 3.14, FastAPI, SQLAlchemy async, Alembic) was written collaboratively with Claude Code
- All frontend code (React 18, TypeScript, MapLibre GL, Tailwind-adjacent CSS variables) was written collaboratively with Claude Code
- All 23 database migrations (PostgreSQL 15 with PostGIS 3.4) were authored by Claude Code with my review
- Schema-tolerant XML/CSV/XLSX/JSON parser for *Jawność* feeds was authored by Claude Code to my specifications
- Warsaw WMS integration (custom `warsaw-wms://` MapLibre protocol, EPSG:4326 tile-to-bbox conversion, GetFeatureInfo XML parsing) was authored by Claude Code to my specifications
- PostGIS spatial join pipeline for district resolution was authored by Claude Code
- POI ingestion from OpenStreetMap Overpass API was authored by Claude Code

**My role throughout:** product vision, architectural decisions, data validation, specification of detailed requirements, review of generated code, debugging direction when Claude Code's first-pass output was incorrect or insufficient, iteration on prompts and requirements when output quality fell short. All judgement calls about what to build, what to prioritise, and whether output was correct were mine.

The working pattern was persistent context sessions of 1–4 hours. Typical interaction: specify a feature or fix, review the generated implementation, validate against live data or browser, iterate. Claude Code does not have persistent memory between sessions; I maintained continuity via a `CLAUDE.md` operating instructions file committed to the repo.

---

## 2. Production Claude usage (inside the platform at runtime)

Three Claude models are called by the platform at runtime:

### Haiku 4.5 — news triage
Scores scraped Polish news articles (Eurobuild CEE, inwestycje.pl) for Poland/Warsaw real estate relevance on a 0–10 scale. Articles scoring ≥6 proceed to Sonnet extraction. Approximately 134 articles scored. Cost: ~$0.02 per article.

**Prompt type:** zero-shot classification with structured JSON output. The system prompt encodes what constitutes "Warsaw RE relevance" (transactions, zoning, policy, development activity) vs. noise (national macro, non-RE sectors, international news).

### Sonnet 4.6 — fact extraction
Extracts typed facts from triage-passed articles into 8 structured fact tables: `supply_events`, `capital_markets_events`, `regulatory_events`, `macro_signals`, `tenant_signals`, `demand_signals`, `market_commentary`, `infrastructure_events`. Approximately 46 articles processed into 456 total fact rows. Cost: ~$0.06 per article.

**Prompt type:** structured extraction with Pydantic schema enforcement. Each fact type has a typed schema; Sonnet is instructed to emit zero facts rather than hallucinate if no evidence is present in the article.

### Opus 4.6 — weekly brief synthesis
Synthesises weekly Warsaw RE research briefs from the 313 geo-filtered facts in the 8 fact tables. Outputs 800–1,200 word structured briefs in English and Polish, saved as PDF and JSON. Cost: ~$0.65 per brief generation.

**Prompt type:** synthesis with editorial persona. The system prompt establishes an editorial voice ("senior Warsaw RE analyst writing for institutional investors"), specifies section structure, and instructs the model to cite source articles by title and date.

**Total production AI cost during development:** approximately $30–50.

---

## 3. Claude in chat (strategic and editorial work)

Throughout the project I used Claude in chat (claude.ai, various models) for:

- Product positioning and framing decisions
- Editorial voice tuning for the weekly brief synthesis prompt
- Prompt engineering iteration for triage and extraction prompts
- README and documentation drafting (this file included — initial drafts were Claude-assisted, then edited by me for accuracy)
- Decision frameworks (e.g., pivoting from Saudi Arabia to Warsaw, prioritising features before the demo)
- Debugging direction when Claude Code stalled on a problem
- Market research synthesis on Polish RE market structure

---

## 4. Claude Design (early visual iteration)

Claude Design (Anthropic's UI design tool) was used in early project phases to iterate on visual design vocabulary — palette, typography scale, card/panel layout conventions. The final implementation was code-only (no design file handoff), but the visual language established via Claude Design informed the CSS variable system and component structure that Claude Code subsequently built.

---

## What was unambiguously human-driven

While AI was used extensively, the following decisions and work were mine:

- **Identification of the Polish Jawność wedge** as the unique data opportunity for this project
- **Decision to pivot from Saudi Arabia to Warsaw** mid-course, and the strategic rationale for it
- **Architectural decisions**: Postgres + PostGIS over alternatives; custom MapLibre WMS protocol over a proxy; agentic pipeline over a batch ETL; multi-model routing (Haiku/Sonnet/Opus by task type) over a single model
- **Demo plot selection and underwriting model calibration**: the PLN 61,868/m² residual land value for ul. Towarowa 28 was ground-truthed against real Warsaw assemblages; the 60/40 residential/commercial exit blend for U(MW) zoning was researched against actual Warsaw mixed-use market evidence
- **Customer persona definitions**: Polish residential developers, foreign capital (family offices and institutional), Warsaw-based asset managers
- **Strategic positioning**: €399/seat pricing hypothesis, post-CS153 customer development plan, FINN bill timing thesis
- **Saudi Arabia version as architectural foundation**: also my work, also developed with Claude Code, for my professional role at White Star Real Estate

---

## Process and iteration disclosure

Development was iterative and sometimes required significant course correction. Claude Code's first-pass output was wrong or insufficient in numerous documented cases. Examples:

- WMS GetFeatureInfo initially returned empty results due to a too-small BBOX. Required several iterations to arrive at a zoom-aware BBOX calculation that produced populated responses.
- The demo plot's initial zoning seed data was fabricated (see LIMITATIONS.md, Failure 1). This was only caught after WMS integration was complete and a visual comparison was possible.
- Section I underwriting blew out to PLN 137,758/m² after updating to real WMS parameters (see LIMITATIONS.md, Failure 2). Required explicit recalibration of build cost and exit pricing assumptions.
- *Jawność* parser artifacts introduced implausible price-move events. Required adding sanity filters after spotting anomalies in the feed output.

These failures are documented in [LIMITATIONS.md](./LIMITATIONS.md) rather than hidden. They represent real engineering iterations, not fabricated process.
