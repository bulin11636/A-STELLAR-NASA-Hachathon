import type { ErrorEnvelope } from "../types/api.ts";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number | null = null,
    public readonly details: ErrorEnvelope["error"]["details"] = null,
  ) { super(message); this.name = "ApiError"; }
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = body.error;
  return typeof error === "object" && error !== null &&
    "code" in error && typeof error.code === "string" && error.code.length > 0 &&
    "message" in error && typeof error.message === "string" && error.message.length > 0 &&
    "details" in error;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

// One transport for all application API calls. NASA WMTS remains independent.
export async function apiRequest<T>(
  path: `/api/v1/${string}`,
  decode: (body: unknown) => T,
  { method = "GET", body, signal, timeoutMs = 20_000 }: RequestOptions = {},
): Promise<T> {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      method,
      headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal,
    });
    let payload: unknown;
    try { payload = await response.json(); }
    catch {
      if (signal?.aborted || timeout.signal.aborted) throw new DOMException("Aborted", "AbortError");
      throw new ApiError(
        response.ok ? "The API returned invalid JSON." : `Backend request failed (HTTP ${response.status}); no valid JSON error was returned. Check that the backend is running.`,
        response.ok ? "INVALID_RESPONSE" : "HTTP_ERROR", response.status,
      );
    }
    if (!response.ok) {
      if (isErrorEnvelope(payload)) {
        throw new ApiError(payload.error.message, payload.error.code, response.status, payload.error.details);
      }
      throw new ApiError(`Backend request failed (HTTP ${response.status}) with an invalid error envelope.`, "INVALID_RESPONSE", response.status);
    }
    try { return decode(payload); }
    catch (error) {
      throw new ApiError(error instanceof Error ? error.message : "The API response does not match the contract.", "INVALID_RESPONSE", response.status);
    }
  } catch (error) {
    if (signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
    if (timeout.signal.aborted) throw new ApiError("The backend request timed out. Please retry.", "TIMEOUT");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Cannot reach the backend. Check your connection and that FastAPI is running on port 8000.", "NETWORK_ERROR");
  } finally { clearTimeout(timer); }
}
