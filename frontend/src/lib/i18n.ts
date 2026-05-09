/**
 * Minimal i18n context — English/Arabic toggle with RTL layout support.
 *
 * shadcn/ui (post Jan 2026) handles physical→logical CSS class transforms.
 * This module handles:
 *   - `dir` attribute on <html>
 *   - Latin number spans in RTL text (wrap in <span dir="ltr">)
 *   - Language preference persistence in localStorage
 */

export type Lang = "en" | "ar";

const STORAGE_KEY = "ws_lang";

export function getStoredLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "ar" ? "ar" : "en";
}

export function setLang(lang: Lang): void {
  localStorage.setItem(STORAGE_KEY, lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

/** Wrap a Latin numeric string so it doesn't flip in RTL context. */
export function ltrSpan(value: string): string {
  return `<span dir="ltr">${value}</span>`;
}
