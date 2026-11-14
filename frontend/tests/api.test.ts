import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { COORDINATE_SYSTEM, type PlanRouteRequest } from "../src/types/api.ts";
import { apiRequest, ApiError } from "../src/services/apiClient.ts";
import { decodeRouteResponse, getHealth, planRoute } from "../src/services/routes.ts";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const request: PlanRouteRequest = {
  region_id: "jezero", coordinate_system: COORDINATE_SYSTEM,
  start: { longitude: 77.42, latitude: 18.44 }, goal: { longitude: 77.48, latitude: 18.46 }, mode: "safest",
};
function response() {
  return {
    status: "success", route_id: "demo-jezero-001", region_id: "jezero",
    coordinate_system: COORDINATE_SYSTEM, mode: "safest", source: "mock",
    route: [request.start, { longitude: 77.45, latitude: 18.45 }, request.goal],
    metrics: { distance_m: null, estimated_time_min: null, risk_score: null },
    warnings: ["Demonstration route only. No terrain or astronaut safety evaluation performed."],
  };
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("planRoute sends exactly one relative POST with the canonical JSON and preserves null metrics", async () => {
  let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls += 1;
    assert.equal(url, "/api/v1/routes/plan");
    assert.equal(init?.method, "POST");
    assert.equal((init?.headers as Record<string, string>)["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(init?.body as string), request);
    return json(response());
  };
  const result = await planRoute(request);
  assert.equal(calls, 1);
  assert.deepEqual(result.metrics, { distance_m: null, estimated_time_min: null, risk_score: null });
  assert.equal(result.source, "mock");
});

test("both modes are serialized exactly", async () => {
  globalThis.fetch = async (_url, init) => {
    assert.equal(JSON.parse(init?.body as string).mode, "shortest");
    return json({ ...response(), mode: "shortest" });
  };
  assert.equal((await planRoute({ ...request, mode: "shortest" })).mode, "shortest");
});

test("health uses the canonical v1 endpoint and validates its response", async () => {
  globalThis.fetch = async (url) => {
    assert.equal(url, "/api/v1/health");
    return json({ status: "ok", service: "a-stellar-backend", api_version: "v1" });
  };
  assert.equal((await getHealth()).service, "a-stellar-backend");
});

for (const [status, code] of [[400, "INVALID_ROUTE"], [400, "UNSUPPORTED_COORDINATE_SYSTEM"], [404, "UNKNOWN_REGION"], [422, "VALIDATION_ERROR"], [500, "INTERNAL_ERROR"]] as const) {
  test(`HTTP ${status} ${code} preserves the structured error`, async () => {
    globalThis.fetch = async () => json({ error: { code, message: "Request rejected.", details: { field: "start" } } }, status);
    await assert.rejects(planRoute(request), (error: unknown) => {
      assert(error instanceof ApiError);
      assert.equal(error.code, code);
      assert.equal(error.status, status);
      assert.deepEqual(error.details, { field: "start" });
      return true;
    });
  });
}

test("invalid inputs and equal endpoints never reach the network", async () => {
  globalThis.fetch = async () => { throw new Error("Must not send request"); };
  for (const invalid of [
    { ...request, goal: request.start },
    { ...request, start: { longitude: 360, latitude: 18 } },
    { ...request, start: { longitude: "77", latitude: 18 } },
    { ...request, mode: "fastest" }, { ...request, coordinate_system: "EPSG:4326" },
  ]) {
    await assert.rejects(planRoute(invalid as PlanRouteRequest), { code: "VALIDATION_ERROR" });
  }
});

test("malformed and mismatched successes are rejected before plotting", () => {
  for (const invalid of [
    { ...response(), coordinate_system: "EPSG:4326" },
    { ...response(), mode: "shortest" }, { ...response(), region_id: "gale" },
    { ...response(), route: [request.start] },
    { ...response(), route: [request.goal, request.start] },
    { ...response(), route: [request.start, { longitude: Infinity, latitude: 0 }, request.goal] },
    { ...response(), metrics: { distance_m: 0, estimated_time_min: null, risk_score: null } },
    { ...response(), metrics: {} }, { ...response(), warnings: [] },
    { ...response(), warnings: [""] }, { ...response(), route_id: "" },
  ]) assert.throws(() => decodeRouteResponse(invalid, request));
  assert.equal(decodeRouteResponse(response(), request).route.length, 3);
});

test("invalid JSON and non-contract error bodies produce useful failures", async () => {
  globalThis.fetch = async () => new Response("proxy offline", { status: 500 });
  await assert.rejects(planRoute(request), { code: "HTTP_ERROR", status: 500 });
  globalThis.fetch = async () => new Response("not json", { status: 200 });
  await assert.rejects(planRoute(request), { code: "INVALID_RESPONSE" });
  globalThis.fetch = async () => json({ detail: [] }, 422);
  await assert.rejects(planRoute(request), { code: "INVALID_RESPONSE", status: 422 });
});

test("network errors, timeouts, and intentional cancellation remain distinct", async () => {
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(planRoute(request), { code: "NETWORK_ERROR" });
  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    const fail = () => reject(new DOMException("Aborted", "AbortError"));
    if (init?.signal?.aborted) fail();
    else init?.signal?.addEventListener("abort", fail, { once: true });
  });
  await assert.rejects(apiRequest("/api/v1/health", (value) => value, { timeoutMs: 10 }), { code: "TIMEOUT" });
  const controller = new AbortController();
  const pending = planRoute(request, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});
