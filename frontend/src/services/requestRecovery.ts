import { ApiError } from "./apiClient.ts";
import type { RequestAttemptStatus } from "../types/attempts.ts";

export function requestId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}

export function localAttempt(id: string, state: RequestAttemptStatus["state"], error: ApiError | null = null, attempt = 1): RequestAttemptStatus {
  return { request_id: id, state, attempt, retry_allowed: false, retry_after_seconds: 0,
    error: error ? { code: error.code, message: error.message, details: error.details } : null, updated_at: null };
}

export function asApiError(error: unknown) {
  return error instanceof ApiError ? error : new ApiError("The request did not complete. Check its recorded status before retrying.", "CLIENT_ERROR");
}

export async function inspectFailure(id: string, error: ApiError, load: () => Promise<RequestAttemptStatus>) {
  try { return await load(); }
  catch {
    // A rejected input can have no durable attempt. A lost connection never
    // establishes that the server stopped; keep its outcome uncertain.
    return localAttempt(id, error.status === 400 || error.status === 422 ? "failed" : "unknown", error);
  }
}

export function rememberPending(key: string, value: unknown) {
  try {
    if (typeof sessionStorage === "undefined") return;
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(value));
  } catch { /* Recovery still works in this page when browser storage is unavailable. */ }
}

export function readPending(key: string): unknown {
  try {
    if (typeof sessionStorage === "undefined") return null;
    const text = sessionStorage.getItem(key);
    if (!text || text.length > 32768) return null;
    return JSON.parse(text);
  } catch { return null; }
}

export function usageUpdated() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("a0-usage-updated"));
}
