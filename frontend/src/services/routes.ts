import { validateApiCoordinate } from "../geo/marsCoordinates.ts";
import { COORDINATE_SYSTEM, type HealthResponse, type PlanRouteRequest, type PlanRouteResponse } from "../types/api.ts";
import { apiRequest, ApiError } from "./apiClient.ts";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function validateRouteRequest(request: PlanRouteRequest): void {
  if (request.region_id !== "jezero") throw new Error("F1.5 supports region jezero only.");
  if (request.coordinate_system !== COORDINATE_SYSTEM) throw new Error("Unsupported coordinate convention.");
  if (request.mode !== "shortest" && request.mode !== "safest") throw new Error("Choose shortest or safest mode.");
  validateApiCoordinate(request.start);
  validateApiCoordinate(request.goal);
  const waypoints = request.waypoints ?? [];
  if (!Array.isArray(waypoints) || waypoints.length > 16) throw new Error("Use at most 16 ordered waypoints.");
  waypoints.forEach(validateApiCoordinate);
  if (request.start.longitude === request.goal.longitude && request.start.latitude === request.goal.latitude) {
    throw new Error("Start and Goal must be different points.");
  }
}

export function decodeRouteResponse(body: unknown, request: PlanRouteRequest): PlanRouteResponse {
  if (!object(body) || body.status !== "success" ||
      typeof body.route_id !== "string" || !body.route_id.trim() ||
      body.region_id !== request.region_id || body.coordinate_system !== COORDINATE_SYSTEM ||
      body.mode !== request.mode || (body.source !== "mock" && body.source !== "computed") ||
      !Array.isArray(body.route) || body.route.length < 2 || !object(body.metrics) ||
      !Array.isArray(body.warnings) || body.warnings.some((warning) => typeof warning !== "string")) {
    throw new Error("The route response does not match the F1.5 API contract.");
  }
  body.route.forEach(validateApiCoordinate);
  const first = body.route[0];
  const last = body.route[body.route.length - 1];
  if (first.longitude !== request.start.longitude || first.latitude !== request.start.latitude ||
      last.longitude !== request.goal.longitude || last.latitude !== request.goal.latitude) {
    throw new Error("The returned route does not include the requested Start and Goal.");
  }
  for (const key of ["distance_m", "estimated_time_min", "risk_score"] as const) {
    const value = body.metrics[key];
    if (value !== null && (typeof value !== "number" || !Number.isFinite(value) || value < 0 ||
        (key === "risk_score" && value > 1))) {
      throw new Error(`Invalid route metric: ${key}.`);
    }
    if (body.source === "mock" && value !== null) throw new Error("Mock routes must have null metrics.");
  }
  let stopIndex = 0;
  for (const stop of request.waypoints ?? []) {
    const found = body.route.findIndex((point, index) => index >= stopIndex && point.longitude === stop.longitude && point.latitude === stop.latitude);
    if (found < 0) throw new Error("The returned route does not preserve required waypoint order.");
    stopIndex = found + 1;
  }
  if (body.source === "mock" && !body.warnings.some((warning) => (warning as string).trim().length > 0)) {
    throw new Error("Mock routes must include a demonstration warning.");
  }
  if (body.source === "computed" && (body.metrics.distance_m === null || !body.warnings.some((w) => (w as string).trim()))) {
    throw new Error("Computed routes require a measured distance and research limitations.");
  }
  return body as unknown as PlanRouteResponse;
}

export interface PlanRouteOptions {
  idempotencyKey?: string;
  retryAttempt?: number;
}

export function planRoute(request: PlanRouteRequest, signal?: AbortSignal, options: PlanRouteOptions = {}): Promise<PlanRouteResponse> {
  try { validateRouteRequest(request); }
  catch (error) {
    return Promise.reject(new ApiError(error instanceof Error ? error.message : "Invalid route selection.", "VALIDATION_ERROR"));
  }
  if (options.idempotencyKey !== undefined && !/^[A-Za-z0-9_-]{16,64}$/.test(options.idempotencyKey)) {
    return Promise.reject(new ApiError("Invalid idempotency key.", "VALIDATION_ERROR"));
  }
  if (options.retryAttempt !== undefined && (!Number.isInteger(options.retryAttempt) || options.retryAttempt < 1 || !options.idempotencyKey)) {
    return Promise.reject(new ApiError("A retry requires an idempotency key and a positive attempt number.", "VALIDATION_ERROR"));
  }
  return apiRequest("/api/v1/routes/plan", (body) => decodeRouteResponse(body, request), {
    method: "POST", body: request, signal, timeoutMs: 90_000,
    headers: {
      ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
      ...(options.retryAttempt ? { "X-A-Stellar-Retry-Attempt": String(options.retryAttempt) } : {}),
    },
  });
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest("/api/v1/health", (body) => {
    if (!object(body) || body.status !== "ok" || body.service !== "a-stellar-backend" || body.api_version !== "v1") {
      throw new Error("The health response does not match the F1.5 API contract.");
    }
    return body as unknown as HealthResponse;
  }, { signal });
}
