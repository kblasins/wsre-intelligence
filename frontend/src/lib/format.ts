/**
 * Formatting utilities for Saudi real estate data.
 *
 * Key rules enforced here:
 *  - Arabic dates always use Gregorian calendar (ar-SA-u-ca-gregory) — ar-SA
 *    defaults to Umm al-Qura calendar in some browsers which produces confusing dates
 *  - Tabular numerals on all monetary/numeric output for column alignment
 *  - SAR amounts use 0 decimal places (market convention); prices/sqm use 1
 *  - Date format is unambiguous: "14 Apr 2026", never "4/14/26"
 */

/** Format SAR amount: SAR 1,234,567 */
export function formatSAR(value: number, decimals = 0): string {
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Format SAR/sqm/yr: 214.3 SAR/sqm/yr */
export function formatRentPerSqm(value: number): string {
  return `${new Intl.NumberFormat("en-SA", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value)} SAR/sqm/yr`;
}

/** Format a percentage: +4.2% or -1.3% with sign */
export function formatPct(value: number, showSign = false): string {
  const formatted = new Intl.NumberFormat("en-SA", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Math.abs(value));
  const sign = value >= 0 ? (showSign ? "+" : "") : "−";
  return `${sign}${formatted}%`;
}

/** Format a date as "14 Apr 2026" (unambiguous, no locale-specific separators) */
export function formatDate(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d);
}

/** Format a date in Arabic with Gregorian calendar: "١٤ أبريل ٢٠٢٦" */
export function formatDateAr(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  // Force Gregorian calendar — ar-SA defaults to Umm al-Qura in many browsers
  return new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(d);
}

/** Format a large number with K/M suffix: 1,250,000 → "1.25M" */
export function formatLargeNumber(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(0);
}

/** Format sqm area: 12,450 sqm */
export function formatArea(sqm: number): string {
  return `${new Intl.NumberFormat("en-SA").format(Math.round(sqm))} sqm`;
}
