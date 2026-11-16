import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, test } from "node:test";
import { decodeStoredRoute, getStoredRoute, requireMatchingResult } from "../src/services/metadata.ts";
import { decodeRouteResponse } from "../src/services/routes.ts";
import { createRouteOverlay, updateRouteOverlay } from "../src/map/routeOverlay.ts";

// Persisted output from the synthetic metric-plane backend fixture, never NASA observations.
export const fixture = JSON.parse(readFileSync(new URL("./fixtures/computed-route.json", import.meta.url), "utf8"));
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test("computed result and nested stored metadata decode while geographic display is enabled", () => {
  const { result, metadata } = fixture;
  assert.equal(decodeRouteResponse(result, metadata.request).source, "computed");
  assert.deepEqual(decodeStoredRoute(fixture, result.route_id), fixture);
  const { source } = createRouteOverlay();
  updateRouteOverlay(source, null, null, result);
  assert.equal(source.getFeatures().length, 1);
  updateRouteOverlay(source, null, null, { ...result, source: "mock" });
  assert.equal(source.getFeatures().length, 1);
});

test("metadata rejects schema defects, identity, request and artifact inconsistencies", () => {
  for (const mutate of [
    (x: any) => { x.metadata.route_id = "wrong"; },
    (x: any) => { x.metadata.request.start.longitude += .01; },
    (x: any) => { x.metadata.request.mode = "safest"; },
    (x: any) => { x.metadata.scope.dataset_version = "wrong"; },
    (x: any) => { x.metadata.grid.planning_resolution_m[0] = Infinity; },
    (x: any) => { delete x.metadata.policy; },
    (x: any) => { x.metadata.created_at = "2026-11-14T08:00:00+08:00"; },
    (x: any) => { x.metadata.sources[0].provenance_record_id = "wrong"; },
    (x: any) => { x.metadata.grid.mask_artifact_ids.coverage = "wrong"; },
    (x: any) => { x.metadata.artifacts.grid.artifact_id = "wrong"; },
    (x: any) => { x.metadata.grid.width = 1000000; },
    (x: any) => { x.metadata.extra = true; },
  ]) {
    const body = structuredClone(fixture); mutate(body);
    assert.throws(() => decodeStoredRoute(body, fixture.result.route_id));
  }
  assert.throws(() => decodeStoredRoute(fixture, "route-" + "2".repeat(32)));
});

test("POST and GET results agree by value regardless of JSON key order", () => {
  const reordered = Object.fromEntries(Object.entries(fixture.result).reverse());
  requireMatchingResult(fixture, reordered as any);
  assert.throws(() => requireMatchingResult(fixture, { ...fixture.result, metrics: { ...fixture.result.metrics, distance_m: 123 } }));
});

test("typed metadata GET reuses transport, validates IDs and preserves errors and cancellation", async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(url, `/api/v1/routes/${fixture.result.route_id}`);
    assert.equal(init?.method, "GET");
    return Response.json(fixture);
  };
  assert.deepEqual(await getStoredRoute(fixture.result.route_id), fixture);
  globalThis.fetch = async () => { throw new Error("Must not send malformed IDs"); };
  await assert.rejects(getStoredRoute("../private"), { code: "VALIDATION_ERROR" });
  globalThis.fetch = async () => Response.json({ error: { code: "ROUTE_NOT_FOUND", message: "Missing route.", details: null } }, { status: 404 });
  await assert.rejects(getStoredRoute(fixture.result.route_id), { code: "ROUTE_NOT_FOUND", status: 404 });
  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  });
  const controller = new AbortController();
  const pending = getStoredRoute(fixture.result.route_id, controller.signal); controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});

test("ordered waypoint labels accompany computed route geometry", () => {
  const { source } = createRouteOverlay();
  const result = fixture.result;
  updateRouteOverlay(source, null, null, result, [result.route[0], result.route[result.route.length - 1]]);
  assert.deepEqual(source.getFeatures().map(feature => feature.get("kind")), ["route", "waypoint", "waypoint"]);
  assert.deepEqual(source.getFeatures().slice(1).map(feature => feature.get("label")), ["W1", "W2"]);
});
