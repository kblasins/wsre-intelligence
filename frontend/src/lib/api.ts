/**
 * Typed API client — thin wrapper around fetch with error handling.
 *
 * All responses are typed via Zod schemas defined alongside each feature.
 * The base URL is inferred from Vite's proxy in dev (same-origin /api/*),
 * and the production domain in prod builds via the VITE_API_BASE_URL env var.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("ws_token") : null;

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body — use status text
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { method: "GET", ...init }),

  post: <T>(path: string, body: unknown, init?: RequestInit) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
      ...init,
    }),

  patch: <T>(path: string, body: unknown, init?: RequestInit) =>
    request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
      ...init,
    }),

  del: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { method: "DELETE", ...init }),
};
