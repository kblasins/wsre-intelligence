/** TypeScript types for API responses from /api/* endpoints. */

export interface ReitSnapshot {
  ticker: string;
  name: string;
  industrial: "yes" | "no" | "verify";
  snapshot_date: string;
  price_sar: number | null;
  nav_per_unit_sar: number | null;
  nav_discount_pct: number | null;
  distribution_per_unit_sar: number | null;
  occupancy_pct: number | null;
}

export interface Stats {
  reit_snapshots: number;
  transactions: number;
  listings: number;
  news_articles: number;
  rent_index: number;
  tenders: number;
}

export interface NewsArticle {
  id: number;
  source: string;
  title_en: string | null;
  title_ar: string | null;
  url: string | null;
  published_at: string | null;
  relevance_score: number | null;
  structured_facts: Record<string, unknown>;
}

export interface BudgetStatus {
  today_usd: number;
  yesterday_usd: number;
  week_usd: number;
  alltime_usd: number;
  today_calls: number;
  daily_cap_usd: number;
  budget_pct: number;
  models: Record<string, number>;
}

export interface PipelineStatus {
  outbox: { pending: number; done: number; permanently_failed: number };
  review_queue: { total: number; pending_review: number };
  news: { triage_backlog: number; extraction_backlog: number; body_fetching_backlog: number };
}

export interface BriefNewsItem {
  headline: string;
  score: number;
  implication: string;
  citation: string | null;
  source: string;
  date: string | null;
}

export interface BriefWatchItem {
  item: string;
  trigger: string;
  timeline: string;
}

export interface BriefMacroItem {
  indicator: string;
  period: string;
  value: string;
  direction: "up" | "down" | "flat";
  implication: string;
  citation: string | null;
}

export interface BriefHighlightItem {
  [key: string]: string | null;
  implication: string;
  citation: string | null;
}

export interface WeeklyBrief {
  id: number;
  week_ending: string;
  brief_text: string;
  brief_json: {
    executive_summary?: string;
    reit_commentary?: string;
    reit_data_gaps?: string[];
    transaction_commentary?: string;
    transaction_data_gaps?: string[];
    warehouse_commentary?: string;
    warehouse_data_gaps?: string[];
    news_intelligence?: BriefNewsItem[];
    macro_highlights?: BriefMacroItem[];
    regulatory_highlights?: BriefHighlightItem[];
    supply_highlights?: BriefHighlightItem[];
    demand_highlights?: BriefHighlightItem[];
    watch_list?: BriefWatchItem[];
  };
  model_id: string;
  cost_usd: number;
  generated_at: string;
  pdf_uri: string | null;
}

export interface Transaction {
  id: number;
  transaction_date: string;
  district: string;
  city: string;
  property_type: string;
  transaction_type: string;
  area_sqm: number | null;
  price_sar: number;
  source_priority: number;
  confidence: number | null;
}

export interface RentIndexEntry {
  id: number;
  district: string | null;
  city: string;
  property_type: string;
  period: string;
  rent_sar_sqm_annual: number | null;
  yoy_change_pct: number | null;
  vacancy_pct: number | null;
  source: string;
  source_priority: number;
}

export interface Tender {
  id: number;
  etimad_id: string;
  entity_name: string | null;
  title_ar: string | null;
  title_en: string | null;
  value_sar: number | null;
  published_at: string | null;
  deadline_at: string | null;
}

export interface Listing {
  id: number;
  portal: string;
  listing_type: string;
  property_type: string;
  district: string | null;
  city: string;
  area_sqm: number | null;
  price_sar: number | null;
  rent_sar_annual: number | null;
  listed_at: string | null;
  is_active: boolean;
  url: string | null;
}
