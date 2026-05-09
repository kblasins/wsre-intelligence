import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type {
  BudgetStatus,
  NewsArticle,
  PipelineStatus,
  ReitSnapshot,
  RentIndexEntry,
  Stats,
  Tender,
  WeeklyBrief,
} from "../types/api";

export function useReitSnapshots() {
  return useQuery<ReitSnapshot[]>({
    queryKey: ["reit-snapshots-latest"],
    queryFn: () => api.get<ReitSnapshot[]>("/api/reit-snapshots/latest"),
  });
}

export function useStats() {
  return useQuery<Stats>({
    queryKey: ["stats"],
    queryFn: () => api.get<Stats>("/api/stats"),
    refetchInterval: 60_000, // refresh counts every minute
  });
}

export function useNews(limit = 20, q?: string) {
  const params = new URLSearchParams({ limit: String(limit), min_relevance: "0" });
  if (q) params.set("q", q);
  return useQuery<NewsArticle[]>({
    queryKey: ["news", limit, q ?? ""],
    queryFn: () => api.get<NewsArticle[]>(`/api/news?${params}`),
  });
}

export function useBudgetStatus() {
  return useQuery<BudgetStatus>({
    queryKey: ["admin-budget"],
    queryFn: () => api.get<BudgetStatus>("/api/admin/budget"),
    refetchInterval: 5 * 60_000,
  });
}

export function usePipelineStatus() {
  return useQuery<PipelineStatus>({
    queryKey: ["admin-pipeline"],
    queryFn: () => api.get<PipelineStatus>("/api/admin/pipeline"),
    refetchInterval: 60_000,
  });
}

export function useRentIndex(propertyType?: string) {
  const params = propertyType ? `?property_type=${propertyType}` : "";
  return useQuery<RentIndexEntry[]>({
    queryKey: ["rent-index", propertyType],
    queryFn: () => api.get<RentIndexEntry[]>(`/api/rent-index${params}`),
    refetchInterval: 10 * 60_000,
  });
}

export function useLatestBrief() {
  return useQuery<WeeklyBrief>({
    queryKey: ["brief-latest"],
    queryFn: () => api.get<WeeklyBrief>("/api/briefs/latest"),
    retry: false, // 404 = no brief yet; don't hammer
    refetchInterval: 5 * 60_000, // check every 5 min
  });
}

export interface BriefSummary {
  id: number;
  week_ending: string;
  executive_summary: string;
  model_id: string;
  cost_usd: number;
  generated_at: string;
  has_pdf: boolean;
}

export function useBriefsList() {
  return useQuery<BriefSummary[]>({
    queryKey: ["briefs-list"],
    queryFn: () => api.get<BriefSummary[]>("/api/briefs"),
    retry: false,
    refetchInterval: 5 * 60_000,
  });
}

export function useTenders(limit = 50) {
  return useQuery<Tender[]>({
    queryKey: ["tenders", limit],
    queryFn: () => api.get<Tender[]>(`/api/tenders?limit=${limit}`),
    refetchInterval: 30 * 60_000,
  });
}

export function useBrief(id: number | null) {
  return useQuery<WeeklyBrief>({
    queryKey: ["brief", id],
    queryFn: () => api.get<WeeklyBrief>(`/api/briefs/${id}`),
    enabled: id !== null,
    retry: false,
  });
}

export interface JobStatus {
  source_key: string;
  display_name: string;
  source_type: string;
  is_enabled: boolean;
  last_attempt_at: string | null;
  last_success_at: string | null;
  age_hours: number | null;
  consecutive_failures: number;
  stale: boolean;
}

export function useJobs() {
  return useQuery<JobStatus[]>({
    queryKey: ["admin-jobs"],
    queryFn: () => api.get<JobStatus[]>("/api/admin/jobs"),
    refetchInterval: 60_000,
  });
}

export interface ScheduleEntry {
  id: string;
  next_fire_time: string | null;
  minutes_until: number | null;
}

export function useSchedule() {
  return useQuery<ScheduleEntry[]>({
    queryKey: ["admin-schedule"],
    queryFn: () => api.get<ScheduleEntry[]>("/api/admin/schedule"),
    refetchInterval: 60_000,
  });
}

export interface CircuitBreakerStatus {
  name: string;
  state: "closed" | "open" | "half-open" | "unknown";
  fail_counter: number;
  fail_max: number;
  reset_timeout_s: number;
}

export function useCircuitBreakers() {
  return useQuery<CircuitBreakerStatus[]>({
    queryKey: ["admin-circuit-breakers"],
    queryFn: () => api.get<CircuitBreakerStatus[]>("/api/admin/circuit-breakers"),
    refetchInterval: 30_000,
  });
}

export interface TransactionAggregate {
  month: string;
  count: number;
  total_sar: number;
  avg_price_sar: number | null;
}

export interface DaySpend {
  day: string;
  spend_usd: number;
  calls: number;
}

export interface LLMCallRow {
  id: number;
  model_id: string;
  task_type: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number;
  is_batch: boolean;
  success: boolean;
  called_at: string;
}

export interface TaskBreakdown {
  task_type: string;
  calls: number;
  spend_usd: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
}

export function useBudgetByTask(days = 7) {
  return useQuery<TaskBreakdown[]>({
    queryKey: ["admin-budget-by-task", days],
    queryFn: () => api.get<TaskBreakdown[]>(`/api/admin/budget/by-task?days=${days}`),
    refetchInterval: 5 * 60_000,
  });
}

export interface DistrictGroup {
  canonical_id: number;
  name_en: string | null;
  name_ar: string | null;
  city: string;
  aliases: Array<{ alias: string; lang: string; source: string | null }>;
}

export function useAdminDistricts(city?: string) {
  const qs = city ? `?city=${encodeURIComponent(city)}` : "";
  return useQuery<DistrictGroup[]>({
    queryKey: ["admin-districts", city ?? ""],
    queryFn: () => api.get<DistrictGroup[]>(`/api/admin/districts${qs}`),
    refetchInterval: 5 * 60_000,
  });
}

export function useLLMCalls(limit = 100) {
  return useQuery<LLMCallRow[]>({
    queryKey: ["admin-llm-calls", limit],
    queryFn: () => api.get<LLMCallRow[]>(`/api/admin/llm-calls?limit=${limit}`),
    refetchInterval: 30_000,
  });
}

export function useBudgetHistory(days = 14) {
  return useQuery<DaySpend[]>({
    queryKey: ["admin-budget-history", days],
    queryFn: () => api.get<DaySpend[]>(`/api/admin/budget/history?days=${days}`),
    refetchInterval: 5 * 60_000,
  });
}

export interface FailedOutboxRow {
  id: number;
  source: string;
  raw_uri: string;
  retry_count: number;
  extraction_error: string | null;
  fetched_at: string;
}

export function useFailedOutbox() {
  return useQuery<FailedOutboxRow[]>({
    queryKey: ["admin-outbox-failed"],
    queryFn: () => api.get<FailedOutboxRow[]>("/api/admin/outbox/failed"),
    refetchInterval: 60_000,
  });
}

export interface ListingsAggregate {
  district: string;
  property_type: string;
  count: number;
  avg_rent_sar_annual: number | null;
  avg_area_sqm: number | null;
  avg_rent_per_sqm: number | null;
}

export interface NewsVolumeRow {
  week: string;
  source: string;
  count: number;
}

export function useNewsVolume(weeks = 12, minRelevance = 0) {
  const qs = new URLSearchParams({ weeks: String(weeks), min_relevance: String(minRelevance) });
  return useQuery<NewsVolumeRow[]>({
    queryKey: ["news-volume", weeks, minRelevance],
    queryFn: () => api.get<NewsVolumeRow[]>(`/api/news/volume?${qs}`),
    refetchInterval: 10 * 60_000,
  });
}

export function useListingsAggregate(params?: {
  listing_type?: string;
  property_type?: string;
  city?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.listing_type) qs.set("listing_type", params.listing_type);
  if (params?.property_type) qs.set("property_type", params.property_type);
  if (params?.city) qs.set("city", params.city);
  const query = qs.toString();
  return useQuery<ListingsAggregate[]>({
    queryKey: ["listings-aggregate", query],
    queryFn: () =>
      api.get<ListingsAggregate[]>(`/api/listings/aggregate${query ? `?${query}` : ""}`),
    refetchInterval: 10 * 60_000,
  });
}

export function useTransactionAggregate(params?: {
  district?: string;
  property_type?: string;
  transaction_type?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.district) qs.set("district", params.district);
  if (params?.property_type) qs.set("property_type", params.property_type);
  if (params?.transaction_type) qs.set("transaction_type", params.transaction_type);
  const query = qs.toString();
  return useQuery<TransactionAggregate[]>({
    queryKey: ["tx-aggregate", query],
    queryFn: () =>
      api.get<TransactionAggregate[]>(`/api/transactions/aggregate${query ? `?${query}` : ""}`),
    refetchInterval: 10 * 60_000,
  });
}


export interface VelocityRow {
  district_key: string;
  district_name: string;
  property_type: string;
  tx_count: number;
  avg_price_per_sqm: number | null;
  avg_momentum_pct: number | null;
  latest_month: string | null;
  window_days: number;
}

export function useDistrictVelocity(property_type?: string, window_days = 90) {
  const params = new URLSearchParams();
  if (property_type) params.set("property_type", property_type);
  params.set("window_days", String(window_days));
  const qs = `?${params.toString()}`;
  return useQuery<VelocityRow[]>({
    queryKey: ["district-velocity", property_type, window_days],
    queryFn: () => api.get<VelocityRow[]>(`/api/spatial/velocity${qs}`),
    refetchInterval: 60 * 60_000, // hourly — refreshed weekly in practice
    staleTime: 30 * 60_000,
  });
}
