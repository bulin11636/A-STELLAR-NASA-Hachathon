import schema from "../types/storedRoute.schema.json";
import type { RouteMetadata, StoredRouteResponse } from "../types/routeMetadata.ts";
import type { PlanRouteRequest, PlanRouteResponse } from "../types/api.ts";
import { ApiError, apiRequest } from "./apiClient.ts";
import { decodeRouteResponse, validateRouteRequest } from "./routes.ts";

// The finite, closed JSON schema is generated from the server's Pydantic models.
// Support the exact vocabulary emitted by this schema; fail closed on unknown shapes.
type Schema = { [key: string]: unknown };
function check(value: unknown, rule: Schema, root: Schema = schema as Schema): boolean {
  if (typeof rule.$ref === "string") {
    const name = rule.$ref.split("/").at(-1)!;
    return check(value, (root.$defs as Record<string, Schema>)[name], root);
  }
  if (Array.isArray(rule.anyOf)) return rule.anyOf.some((r) => check(value, r, root));
  if ("const" in rule && value !== rule.const) return false;
  if (Array.isArray(rule.enum) && !rule.enum.includes(value)) return false;
  if (rule.type === "null") return value === null;
  if (rule.type === "boolean") return typeof value === "boolean";
  if (rule.type === "string") return typeof value === "string" &&
    (typeof rule.minLength !== "number" || value.length >= rule.minLength) &&
    (typeof rule.maxLength !== "number" || value.length <= rule.maxLength) &&
    (typeof rule.pattern !== "string" || new RegExp(rule.pattern).test(value)) &&
    (rule.format !== "date-time" || /(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value)));
  if (rule.type === "number" || rule.type === "integer") return typeof value === "number" && Number.isFinite(value) &&
    (rule.type !== "integer" || Number.isInteger(value)) &&
    (typeof rule.minimum !== "number" || value >= rule.minimum) &&
    (typeof rule.maximum !== "number" || value <= rule.maximum) &&
    (typeof rule.exclusiveMinimum !== "number" || value > rule.exclusiveMinimum) &&
    (typeof rule.exclusiveMaximum !== "number" || value < rule.exclusiveMaximum);
  if (rule.type === "array") {
    if (!Array.isArray(value) || typeof rule.minItems === "number" && value.length < rule.minItems ||
        typeof rule.maxItems === "number" && value.length > rule.maxItems) return false;
    if (Array.isArray(rule.prefixItems)) return value.every((v, i) => check(v, (rule.prefixItems as Schema[])[i], root));
    return value.every((v) => check(v, rule.items as Schema, root));
  }
  if (rule.type === "object") {
    if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
    const obj = value as Record<string, unknown>;
    const properties = (rule.properties ?? {}) as Record<string, Schema>;
    if (Array.isArray(rule.required) && rule.required.some((key) => !(key in obj))) return false;
    return Object.entries(obj).every(([key, v]) => key in properties ? check(v, properties[key], root) :
      rule.additionalProperties === false ? false : typeof rule.additionalProperties === "object" ? check(v, rule.additionalProperties as Schema, root) : true);
  }
  return "const" in rule || "enum" in rule;
}

export function decodeStoredRoute(body: unknown, routeId: string): StoredRouteResponse {
  if (!check(body, schema as Schema)) throw new Error("Stored route metadata does not match the API schema.");
  const stored = body as StoredRouteResponse;
  const { result, metadata: m } = stored;
  if (m.request.region_id !== "jezero") throw new Error("Stored region mismatch.");
  const request = m.request as PlanRouteRequest;
  validateRouteRequest(request);
  decodeRouteResponse(result, request);
  if (result.route_id !== routeId || m.route_id !== routeId || result.source !== "computed" ||
      result.metrics.distance_m === null || m.validation.status !== "passed" ||
      !m.sources.length || m.scope.dataset_version !== m.sources[0].sha256 || m.scope.region_id !== result.region_id ||
      m.grid.wire_convention !== result.coordinate_system ||
      m.grid.width * m.grid.height > m.policy.limits.max_grid_cells ||
      Object.keys(m.grid.mask_artifact_ids).sort().join(",") !== "blocked,coverage,unknown" ||
      Object.entries(m.grid.mask_artifact_ids).some(([role, id]) => id !== `${routeId}:grid#${role}`) ||
      Object.keys(m.artifacts).sort().join(",") !== "grid,provenance,validation" ||
      Object.entries(m.artifacts).some(([role, artifact]) => artifact.artifact_id !== `${routeId}:${role}`) ||
      m.sources[0].provenance_record_id !== `${routeId}:provenance`) {
    throw new Error("Stored route identity or metadata is inconsistent.");
  }
  if (m.assessment) {
    const expected=m.assessment.time?.total_min ?? null, actual=result.metrics.estimated_time_min;
    if ((expected === null) !== (actual === null) || expected !== null && actual !== null && Math.abs(expected-actual) > 1e-9*Math.max(1,Math.abs(expected))) throw new Error("Walking assessment and route time disagree.");
    if (m.assessment.time) {
      const estimate=m.assessment.time, mission=m.request.mission;
      if (!mission || mission.speed_m_s !== estimate.speed_m_s) throw new Error("Walking estimate requires matching explicit mission assumptions.");
      const travel=result.metrics.distance_m!/mission.speed_m_s!/60, stop=m.request.waypoints.length*mission.stop_minutes_per_waypoint;
      if ([[estimate.travel_min,travel],[estimate.stop_min,stop],[estimate.total_min,travel+stop]].some(([a,b])=>Math.abs(a-b)>1e-9*Math.max(1,Math.abs(b)))) throw new Error("Walking estimate does not match the route distance and dwell assumptions.");
    }
  }
  return stored;
}

export { check as checkSchema };

// Compare JSON values independent of object key ordering; arrays retain their order.
function sameJson(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => sameJson(v, b[i]));
  if (typeof a !== "object" || a === null || typeof b !== "object" || b === null || Array.isArray(a) || Array.isArray(b)) return false;
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>;
  return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every((key) => Object.hasOwn(right, key) && sameJson(left[key], right[key]));
}

export function requireMatchingResult(stored: StoredRouteResponse, planned: PlanRouteResponse): void {
  if (!sameJson(stored.result, planned)) throw new Error("Stored result differs from the planned result.");
}

export function getStoredRoute(routeId: string, signal?: AbortSignal): Promise<StoredRouteResponse> {
  if (!/^route-[a-f0-9]{32}$/.test(routeId)) return Promise.reject(new ApiError("Invalid route identifier.", "VALIDATION_ERROR"));
  return apiRequest(`/api/v1/routes/${routeId}`, (body) => decodeStoredRoute(body, routeId), { signal });
}

export type { RouteMetadata, StoredRouteResponse };
