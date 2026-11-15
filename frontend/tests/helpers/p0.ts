import { readFileSync } from "node:fs";
import type { PlanRouteRequest } from "../../src/types/api.ts";

export const fixture = JSON.parse(readFileSync(new URL("../fixtures/computed-route.json", import.meta.url), "utf8"));
export function storedFor(request: PlanRouteRequest, digit = "1") {
  const stored = JSON.parse(JSON.stringify(fixture).replaceAll(fixture.result.route_id, "route-" + digit.repeat(32)));
  stored.result.mode = request.mode;
  stored.metadata.request = { ...structuredClone(request), waypoints: request.waypoints ?? [], mission: request.mission ?? null };
  return stored;
}
export function attempt(id: string, state = "failed", retry = true, version = 1, seconds = 0) {
  return { request_id: id, state, attempt: version, retry_allowed: state === "failed" && retry && !seconds, retry_after_seconds: seconds,
    error: state === "failed" || state === "unknown" ? { code: "A0_RATE_LIMITED", message: "Recorded request failure.", details: null } : null, updated_at: "2026-11-15T00:00:00Z" };
}
export function failure(code = "A0_RATE_LIMITED") {
  return Response.json({ error: { code, message: "Recorded request failure.", details: null } }, { status: 503 });
}
export function answer(routeId: string, body: any) {
  return { message_id: body.request_id, route_id: routeId, created_at: "2026-11-15T00:00:00Z", user_message: body.message,
    assistant_message: "Terrain-only explanation.", result: null, metadata: null, specialist_trace: [], usage: null };
}
export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
export function sessionMemory() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) };
}
