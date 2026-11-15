import { ApiError, apiRequest } from "./apiClient.ts";
import { REQUEST_ID_PATTERN, type RequestAttemptStatus } from "../types/attempts.ts";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validError(value: unknown): boolean {
  return value === null || (object(value) && typeof value.code === "string" && value.code.length > 0 &&
    typeof value.message === "string" && value.message.length > 0 && "details" in value);
}

export function decodeRequestAttemptStatus(body: unknown): RequestAttemptStatus {
  if (!object(body) || typeof body.request_id !== "string" || !REQUEST_ID_PATTERN.test(body.request_id) ||
      !["running", "succeeded", "failed", "unknown"].includes(body.state as string) ||
      !Number.isInteger(body.attempt) || (body.attempt as number) < 1 ||
      typeof body.retry_allowed !== "boolean" || !Number.isInteger(body.retry_after_seconds) ||
      (body.retry_after_seconds as number) < 0 || !validError(body.error) ||
      (body.updated_at !== null && typeof body.updated_at !== "string")) {
    throw new Error("Invalid request attempt status.");
  }
  return body as unknown as RequestAttemptStatus;
}

function validRequestId(requestId: string) {
  if (!REQUEST_ID_PATTERN.test(requestId)) throw new ApiError("Invalid request identifier.", "VALIDATION_ERROR");
}

function validRouteId(routeId: string) {
  if (!/^route-[a-f0-9]{32}$/.test(routeId)) throw new ApiError("Invalid route identifier.", "VALIDATION_ERROR");
}

export function getPlanRequestStatus(requestId: string, signal?: AbortSignal): Promise<RequestAttemptStatus> {
  validRequestId(requestId);
  return apiRequest(`/api/v1/routes/requests/${requestId}`, body => {
    const value = decodeRequestAttemptStatus(body);
    if (value.request_id !== requestId) throw new Error("Request status identity mismatch.");
    return value;
  }, { signal });
}

export function getChatAttemptStatus(routeId: string, requestId: string, signal?: AbortSignal): Promise<RequestAttemptStatus> {
  validRouteId(routeId); validRequestId(requestId);
  return apiRequest(`/api/v1/routes/${routeId}/chat/attempts/${requestId}`, body => {
    const value = decodeRequestAttemptStatus(body);
    if (value.request_id !== requestId) throw new Error("Request status identity mismatch.");
    return value;
  }, { signal });
}
