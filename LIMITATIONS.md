# Limitations, Known Issues & Failure Analysis

This document is an honest account of what doesn't work, what's incomplete, and what failed during development. It is written for CS 153 reviewers evaluating the project's Process, Integrity & Disclosure components.

---

## Data Coverage Limitations

### Jawność ingestion coverage

The *Jawność cen mieszkań* feed covers approximately 1,000 national developers, 200+ in Warsaw. The platform has ingested 85,130 dwelling rows from 1,351 developers into `primary_pricing`. Known gaps:

| Issue | Affected developers | Status |
|---|---|---|
| Dataset expired (all units sold, no active inventory) | Echo Investment (Warsaw 2025 datasets) | Excluded — expected behaviour |
| HTTP 406 errors from data host | Murapol, Okam | Not ingested; logged in `jawnosc_developers.last_sync_status` |
| SSL certificate failure | Ronson Development | Not ingested |
| Not yet onboarded to dane.gov.pl per the new law | Cordia, ED Invest, Eiffage, Matexi, Modecom, Polnord, Yareal | Not ingested; legal compliance timeline unknown |
| Non-standard XLSX schema (unresolvable column mapping) | ~20 non-priority developers | ~37,803 rows excluded via `m2_price > 1,000` sanity filter |

The platform covers approximately 17 of 30 priority Warsaw-active firms. Firm-level coverage is visible in the Admin page ingestion status table.

### Section B: Land comparable transactions

Warsaw RCN (*Rejestr Cen Nieruchomości*) historical transaction data is not yet ingested. Section B in the Plot Evaluation panel uses **10 hand-seeded demo rows** for ul. Towarowa 28, stored in `plot_land_comps_seed` with `is_demo_seed = TRUE`. These are representative of actual Wola land transaction ranges but are not verified notarial records.

A formal data access request to Główny Urząd Geodezji i Kartografii (GUGiK) for bulk RCN data was submitted in April 2026. The request is pending (estimated 30–90 day response window). Until approved, Section B land comps remain manually seeded for the demo plot only.

### Section E: Demographics

GUS BDL (*Bank Danych Lokalnych*) is not yet integrated. Section E demographics values for the demo plot (population, age distribution, income) are hand-seeded in `plot_demographics_seed`. They are based on published GUS 2024 dzielnica-level data for Wola but are not programmatically refreshed.

### Secondary market transactions

Notarial deed transaction records (*Rejestr Cen Notarialnych*) are not in the pipeline. These are the canonical source for secondary-market price verification in Poland and would significantly strengthen Section B. Pipeline integration is planned but not implemented.

---

## Deployment Limitations

### WMS geo-restriction

Warsaw municipal WMS (`wms.um.warszawa.pl`) geo-restricts to Polish IP addresses. Development was conducted via NordVPN Poland connection. The Workbench map degrades gracefully without Polish IP access: the basemap and POI layers render normally; the MPZP boundary and function layers fail silently with an amber error indicator on the layer toggle.

**Impact for reviewers:** the WMS raster overlay layers (MPZP coverage, MPZP function, GetFeatureInfo popup) will not function without a Polish IP. The Plot Evaluation panel (all 9 sections) is unaffected — it reads from seeded Postgres data, not live WMS.

Production deployment plan: Cloudflare Workers with a Warsaw-region edge node, which would place egress from a Polish IP by default.

### No production deployment

The platform runs locally only. There is no publicly accessible deployment. A demo video is provided in the project submission.

---

## Test Coverage

### Backend test suite broken

226 backend tests fail at setup with `ModuleNotFoundError: No module named 'psycopg2'`. Root cause: `conftest.py` uses synchronous SQLAlchemy (`sa.create_engine`) for test fixture setup, which pulls the psycopg2 dialect. The production application uses asyncpg exclusively; psycopg2 was never installed in the virtual environment. This pre-existing issue was inherited from the Saudi Arabia fork and was not addressed during the project sprint.

An additional collection error exists in `test_news_generic_parser.py` which imports a function `_parse_generic_page` that no longer exists in the news scraper module — a stale test from an earlier scraper API version.

**Neither failure represents a regression introduced by Warsaw-specific work.** All 23 migrations, the plot evaluation service, the WMS integration, and the frontend have been manually validated against a running local instance.

### Frontend: no automated tests

The frontend has no Jest or Playwright automated test coverage. All validation was manual.

### No external user testing

The demo flow has not been validated by anyone other than the author.

---

## Validation Gaps

- No customer interviews with Polish RE developers, family offices, or institutional capital — product positioning is hypothesis-driven
- No benchmarking against JLL Poland, CBRE Poland, Cushman & Wakefield Poland, or Cenatorium research products
- No expert validation from Polish RE practitioners, academics, or regulatory specialists
- Single-user platform; no usage metrics, retention data, or A/B testing
- Brief synthesis quality (Opus 4.6 output) has not been evaluated by a Polish RE domain expert

---

## Documented Failure Analysis

The following failures occurred during development and required course correction. They are documented here rather than omitted, as they represent authentic engineering iterations.

### Failure 1: Demo plot MPZP data fabrication

**What happened:** During the initial plot seed (migration 0011), the demo plot ul. Towarowa 28 was initialised with a fabricated MPZP plan name "Czyste — Towarowa MPZP" with invented parameters: max FAR 5.5, max height 130m, MW residential function code. These values were generated by Claude Code without grounding in real Warsaw data — a hallucination passed into production seed data without adequate verification.

**How it was caught:** After Warsaw BGiK WMS integration was complete, a click-to-detail GetFeatureInfo request at the actual plot coordinates returned the real municipal record: plan `rej. ul. Żelaznej cz. północna A`, function `U(MW)` mixed-use, FAR 12, max height 55m. The discrepancy was immediately visible.

**How it was fixed:** Migration 0021 updated the zoning seed to match WMS reality. Migration 0023 corrected two regulatory event seed items that had referenced the fabricated plan name ("Czyste-Towarowa MPZP") and a fabricated WSA court ruling about a 130m height ceiling.

**Lesson:** Seeded demo data should be grounded in real sources from the start, or clearly marked as placeholder pending verification. The WMS integration should have been built before the seed data, not after.

### Failure 2: Section I underwriting blow-out

**What happened:** After updating the demo plot's zoning seed to real WMS values (FAR 12 instead of originally seeded FAR 5.5), the Section I residual land value calculation produced PLN 137,758/m² — implausibly high for any Warsaw market, let alone for a plot where comparables trade at PLN 3,000–5,000/m².

**Root cause:** The build cost (5,500 PLN/m² PUM) and exit price (residential-only at ~20,034 PLN/m²) were inherited from the MW pure-residential calibration. With FAR 12, a pure-residential GDV is enormous, driving an absurd residual. But U(MW) mixed-use plots have a higher build cost (more complex programme) and a lower blended exit price (commercial component discounts the residential premium).

**How it was fixed:** Function-aware build cost resolution (`_resolve_build_cost()`) was added: U(MW) and U zoning codes use 7,500 PLN/m² PUM vs. 5,500 for MW residential. Blended exit pricing (`_resolve_exit_price()`) was added: U(MW) uses 60% residential + 40% commercial (PLN 12,000/m²) blended exit. Final residual: PLN 61,868/m², consistent with premium Wola FAR-12 mixed-use parcel market evidence.

**Lesson:** Underwriting models that derive inputs from a single set of assumptions produce systematically wrong results when applied to a different zoning function. The model needs to be parameter-aware by function code, not just numerically sensitive.

### Failure 3: Jawność price-move feed parser artifacts

**What happened:** The initial Recent Price Changes feed in the Primary Market page included approximately 44 events with implausible deltas: +25% to +58% price increases on individual units in a single day. These appeared as top-ranked "price moves" in the frontend feed.

**Root cause:** The diff algorithm comparing day-over-day prices was reading the wrong column from non-standard XLSX schemas in some developer files. Where the column mapping was ambiguous, the parser was comparing current price against a previous-day value drawn from a different field (e.g., comparing m²-price against total-price).

**How it was fixed:** A ±10% sanity cap was added to the price-change query. This filtered the 44 artefact events while preserving 17 genuine price moves over a 30-day window.

**Lesson:** Pipeline output cannot be trusted on row count alone. Every feed output needs spot-check validation against source data — in this case, cross-referencing the flagged units against the developer's actual published website prices would have caught the artefacts immediately.

### Failure 4: Non-Warsaw leakage in Primary Residential Market

**What happened:** The `/api/primary-market/price-changes` endpoint initially returned price-change events from Kraków, Wrocław, Iława, and other non-Warsaw cities. This was discovered visually when "Jednopiętrowy Kraków sp. z o.o." appeared at the top of the Warsaw market intelligence feed.

**Root cause:** The Warsaw filter was applied at the frontend display level but not at the endpoint query level. The backend returned all cities from `primary_pricing`; the frontend filtered by assumed Warsaw-only developer names, but the assumption broke for multi-city developers.

**How it was fixed:** A `city ILIKE '%warszawa%'` or Warsaw `district` membership filter was enforced at the endpoint level. Single-table filtering is insufficient for a Warsaw-specific product; the filter must be applied to every query that touches `primary_pricing`.

**Lesson:** A Warsaw platform needs Warsaw filtering enforced at every data access layer. Relying on frontend filtering or implicit assumptions about developer geography is fragile.

### Failure 5: Jawność schema coverage rate

**Current state:** 89.6% parse success rate across 16,175 discovered datasets. Approximately 1,678 datasets produce schema-mapping failures or downstream validation errors. These are flagged with `last_sync_status = 'schema_error'` in `jawnosc_developers` and excluded from all aggregates.

The 10.4% failure mode is partly structural: the *Jawność* law specifies a required field list but does not enforce a column naming convention. Polish developers use 30+ variations of "price per m²" (`cena_za_m2`, `cena_m2`, `cena/m2`, `cenaPrzedZmiana`, etc.). The parser handles the most common variants; the long tail is still open.

**Partial fix applied:** The ±10% sanity filter prevents bad rows from corrupting aggregates even when schema mapping partially succeeds. True fix requires either a more exhaustive synonym map or a Sonnet-powered schema normalisation step — the latter is architecturally straightforward but was not prioritised in the sprint.
