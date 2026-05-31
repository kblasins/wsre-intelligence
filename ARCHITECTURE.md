# Architecture

## System Overview

WSRE Intelligence is a three-tier web application: a Python/FastAPI backend, a React/TypeScript frontend, and a PostgreSQL + PostGIS database. An agentic AI pipeline (Haiku → Sonnet → Opus) runs on a weekly scheduler. All components run on a single host in development.

## Data Flow Diagram

```mermaid
graph TD
    subgraph External Sources
        A1[dane.gov.pl<br/>Jawność XML/CSV/XLSX feeds<br/>16,175 datasets]
        A2[BGiK Warsaw WMS<br/>wms.um.warszawa.pl<br/>MPZP zoning layers]
        A3[OpenStreetMap<br/>Overpass API<br/>POI data]
        A4[Eurobuild CEE<br/>inwestycje.pl<br/>Polish RE news]
        A5[GUS BDL<br/>Demographics<br/>planned]
        A6[Warsaw RCN<br/>Land transactions<br/>planned]
    end

    subgraph Ingestion Layer
        B1[jawnosc.py<br/>Dataset discovery + download]
        B2[jawnosc_parser.py<br/>Schema-tolerant XML/CSV/XLSX parser]
        B3[osm_pois.py + overpass.py<br/>POI ingestion]
        B4[polish_news.py<br/>Article scraping]
        B5[osm_districts.py<br/>Warsaw district geometry]
    end

    subgraph AI Pipeline
        C1[Claude Haiku 4.5<br/>News triage scoring<br/>~$0.02/article]
        C2[Claude Sonnet 4.6<br/>Typed fact extraction<br/>~$0.06/article]
        C3[Claude Opus 4.6<br/>Weekly brief synthesis<br/>~$0.65/brief]
    end

    subgraph PostgreSQL + PostGIS
        D1[primary_pricing<br/>85,130 dwelling rows]
        D2[jawnosc_developers<br/>16,175 dataset registry]
        D3[warsaw_pois<br/>5,804 POIs]
        D4[news_articles<br/>134 articles]
        D5[8 fact tables<br/>456 typed RE facts]
        D6[weekly_briefs<br/>PDF + JSON]
        D7[plot seed tables<br/>zoning / comps / demo / infra / regulatory]
        D8[warsaw_districts<br/>18-dzielnica geometry]
    end

    subgraph FastAPI Backend
        E1[/api/workbench/plot/:id<br/>9-section plot evaluation]
        E2[/api/workbench/pois<br/>GeoJSON POI layer]
        E3[/api/primary-market/*<br/>Pricing analytics]
        E4[/api/commercial-market/*<br/>Commercial data]
        E5[/api/briefs/*<br/>Brief CRUD + PDF]
        E6[/api/admin/*<br/>Review queue]
        E7[/api/auth/*<br/>JWT Bearer auth]
        E8[Scheduler<br/>Weekly ingestion + brief generation]
    end

    subgraph React Frontend
        F1[WorkbenchPage<br/>MapLibre map + 9-section eval panel]
        F2[PrimaryMarketPage<br/>Price analytics + heatmap]
        F3[CommercialMarketPage<br/>Commercial market view]
        F4[SubmarketsPage<br/>Dzielnica breakdown]
        F5[BriefsPage<br/>Weekly briefs viewer]
        F6[IntelligencePage<br/>Typed facts feed]
        F7[AdminPage<br/>Review queue]
    end

    subgraph MapLibre Layers
        G1[warsaw-wms:// protocol<br/>Custom tile→EPSG:4326 bbox]
        G2[MPZP boundaries layer<br/>BGiK WMS raster]
        G3[MPZP function layer<br/>BGiK WMS raster]
        G4[GetFeatureInfo popup<br/>Click-to-detail zoning]
        G5[POI vector layers<br/>metro / tram / school / health / park]
    end

    A1 --> B1 --> B2 --> D1
    B2 --> D2
    A3 --> B3 --> D3
    A4 --> B4 --> D4
    A2 --> B5 --> D8
    D4 --> C1 --> C2 --> D5
    D5 --> C3 --> D6
    D1 & D3 & D5 & D7 --> E1
    D3 --> E2
    D1 --> E3
    E1 & E2 & E3 & E4 & E5 & E6 --> F1 & F2 & F3 & F4 & F5 & F6 & F7
    A2 --> G1 --> G2 & G3 & G4
    D3 --> G5
    G2 & G3 & G4 & G5 --> F1
```

---

## Component Overview

### Ingestion Layer (`backend/app/ingestion/`)

**`jawnosc.py`** — Discovers and downloads *Jawność cen mieszkań* datasets from the dane.gov.pl CKAN API. Enumerates all publisher organisations, filters for valid dataset formats (XML, CSV, XLSX), downloads to local blob store, and upserts into `jawnosc_developers` registry. Handles rate limiting and per-developer retry logic.

**`jawnosc_parser.py`** — Schema-tolerant parser for the 30+ field variants observed across 1,000+ Polish developers. Maps heterogeneous column names to a canonical schema, applies sanity filters (price > 1,000 PLN/m²), and upserts into `primary_pricing`. Handles XML, CSV, and XLSX format detection automatically.

**`osm_pois.py` + `overpass.py`** — Queries OpenStreetMap Overpass API for Warsaw metro stations, tram stops, schools, healthcare facilities, parks, and rail stations. Resolves each POI to its canonical Warsaw dzielnica via PostGIS spatial join against `warsaw_districts`. Stores 5,804 POIs in `warsaw_pois`.

**`polish_news.py`** — Scrapes Eurobuild CEE and inwestycje.pl article feeds. Extracts article text, title, date, and source URL. Stores raw articles in `news_articles` table for AI pipeline processing.

**`osm_districts.py`** — Ingests Warsaw 18-dzielnica boundary polygons from OpenStreetMap into PostGIS `warsaw_districts` for spatial joins.

### AI Pipeline (`backend/app/services/`)

**`news_pipeline.py`** — Orchestrates the three-stage AI pipeline. Stage 1: Haiku 4.5 triage (relevance score 0–10, threshold 6). Stage 2: Sonnet 4.6 fact extraction into 8 typed tables. Stage 3: Opus 4.6 weekly brief synthesis from aggregated facts. Budget-gated via configurable monthly/daily PLN limits.

**`plot_evaluation.py`** — Assembles all 9 sections of a Plot Evaluation response for a given `plot_id`. Queries seed tables, primary pricing data, POIs, news facts, and computes Section I underwriting snapshot with function-aware build cost (`_resolve_build_cost()`) and blended exit pricing (`_resolve_exit_price()`).

### API Layer (`backend/app/api/routes/`)

| Route module | Endpoints | Description |
|---|---|---|
| `workbench.py` | `/api/workbench/plot/:id`, `/api/workbench/pois` | Plot evaluation + POI GeoJSON |
| `market.py` | `/api/primary-market/*`, `/api/commercial-market/*` | Market analytics |
| `briefs.py` | `/api/briefs/*` | Brief CRUD, trigger generation, PDF download |
| `admin.py` | `/api/admin/*` | Review queue management |
| `spatial.py` | `/api/spatial/*` | Isochrone and spatial query endpoints |
| `auth.py` | `/api/auth/*`, `/api/users/*` | JWT Bearer auth via fastapi-users |

All endpoints require JWT Bearer authentication. Auth token lifetime: 7 days.

### Frontend (`frontend/src/pages/`)

**`WorkbenchPage.tsx`** (1,400+ lines) — The core product screen. Left rail: saved deals list + layer tree (6 POI categories + 3 WMS toggles + transactions). Centre: MapLibre GL map with Warsaw basemap, WMS MPZP overlays via custom `warsaw-wms://` protocol, POI vector layers, saved deal markers, click-to-detail GetFeatureInfo popup. Right rail: 9-section Plot Evaluation panel or Compare mode side-by-side view.

**`PrimaryMarketPage.tsx`** — Price analytics for Warsaw primary residential market. KPI strip, developer-level heatmap, price-per-m² trends, recent price change feed.

**`BriefsPage.tsx`** — Weekly research brief viewer with PDF download. Triggers Claude Opus synthesis via API.

**`IntelligencePage.tsx`** — Typed facts feed from the 8 fact tables, filterable by category and date.

**`AdminPage.tsx`** — Article review queue for manual triage override, ingestion status, LLM call log.

### MapLibre WMS Integration

A custom `warsaw-wms://` protocol registered with MapLibre converts z/x/y tile coordinates to EPSG:4326 bounding boxes for BGiK WMS `GetMap` requests. This allows standard MapLibre raster tile sources to drive a WMS server that does not support slippy-map tiles natively. GetFeatureInfo requests fire on click with a zoom-aware bbox and parse XML responses for fields: `FUN_SYMB`, `FUN_NAZWA`, `NAZWA_PLAN`, `MAX_WYS`, `INTEN_ZAB`, `WWW`.

### Database Schema

23 Alembic migrations (0001–0023). Key tables:

| Table | Rows | Purpose |
|---|---|---|
| `primary_pricing` | 85,130 | Dwelling-level pricing from *Jawność* feed |
| `jawnosc_developers` | 16,175 | Dataset registry, sync status, schema variant |
| `warsaw_pois` | 5,804 | OSM POIs with PostGIS point geometry |
| `warsaw_districts` | 18 | Dzielnica boundary polygons (PostGIS) |
| `news_articles` | 134 | Scraped Polish RE news articles |
| `supply_events` + 7 others | 456 total | Typed fact tables from Sonnet extraction |
| `plot_zoning_seed` | demo rows | MPZP parameters per plot |
| `plot_land_comps_seed` | demo rows | Land comparable transactions per plot |
| `weekly_briefs` | — | Generated briefs with PDF blob reference |

---

## Data Flow Examples

### Example 1: Jawność price update → UI

1. Scheduler triggers `jawnosc.py` discovery loop
2. dane.gov.pl CKAN API returns updated dataset URLs for registered developers
3. `jawnosc_parser.py` downloads changed datasets, detects format (XML/CSV/XLSX), maps columns to canonical schema
4. Parsed rows upserted into `primary_pricing` with `updated_at` timestamp; previous `status` values preserved; price change recorded in `price_history` JSONB array
5. Frontend `PrimaryMarketPage` calls `/api/primary-market/price-changes?days=30`
6. API queries `primary_pricing` for rows where `price_history` array length > 0 within window, applies ±10% sanity filter
7. Component renders Recent Price Changes feed with developer, investment, Δ%, and date

### Example 2: Article → weekly brief

1. `polish_news.py` scraper runs, fetches new Eurobuild CEE / inwestycje.pl articles, stores in `news_articles`
2. Pipeline calls Haiku 4.5 with article text; receives JSON `{"score": 8, "reason": "..."}`; articles scoring ≥6 flagged for extraction
3. Sonnet 4.6 called with triage-passed article; extracts typed facts per Pydantic schema; 0–N facts per article written to relevant fact tables with `article_id` FK
4. On weekly trigger, Opus 4.6 receives all facts from the past 7 days filtered to Warsaw geography; synthesises 800–1,200 word brief with EN + PL versions
5. Brief saved as JSON + PDF via `BlobStore`; record inserted into `weekly_briefs`; admin notified
6. `BriefsPage` renders brief with PDF download button
