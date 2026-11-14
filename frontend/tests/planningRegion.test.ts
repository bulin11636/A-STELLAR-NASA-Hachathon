import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { COORDINATE_SYSTEM } from "../src/types/api.ts";
import { decodePlanningRegion } from "../src/services/planningRegion.ts";

const stored = JSON.parse(readFileSync(new URL("./fixtures/computed-route.json", import.meta.url), "utf8"));
function response() {
  return { regions: [{ id: "jezero", coordinate_system: COORDINATE_SYSTEM,
    routing_available: true, routing_mode: "computed", planning: {
      roi_id: stored.metadata.scope.roi_id, bounds: stored.metadata.scope.bounds,
      resolution_m: [20, 30], example_request: stored.metadata.request,
    } }] };
}

test("planning footprint accepts matching API endpoints and supports older/mock servers", () => {
  assert.deepEqual(decodePlanningRegion(response()).planning?.example_request, stored.metadata.request);
  const old = response(); delete (old.regions[0] as any).planning;
  assert.equal(decodePlanningRegion(old).planning, null);
  const mock = { regions: [{ ...old.regions[0], routing_mode: "mock", planning: null }] };
  assert.equal(decodePlanningRegion(mock).planning, null);
});

test("planning footprint rejects malformed bounds/resolution and out-of-coverage examples", () => {
  const negative = response(); negative.regions[0].planning.resolution_m[0] = -20;
  const reversed = response(); reversed.regions[0].planning.bounds = { west: 78, east: 77, south: 18, north: 19 };
  const outside = structuredClone(response()); outside.regions[0].planning.example_request.start.longitude = 100;
  for (const body of [negative, reversed, outside, { regions: [] }]) assert.throws(() => decodePlanningRegion(body));
});

test("regional examples use validated source bounds and bounded allocations", () => {
  const body: any = structuredClone(response());
  const info = body.regions[0].planning;
  info.source_bounds = { west:76,east:79,south:17,north:20 };
  info.dynamic_windowing = true; info.max_grid_cells = 1_000_000;
  info.regional_example_request = structuredClone(stored.metadata.request);
  info.regional_example_request.start.longitude = 76.5;
  assert(decodePlanningRegion(body).planning?.regional_example_request);
  for (const mutate of [
    (x: any) => { x.source_bounds.west = '76'; },
    (x: any) => { x.source_bounds.east = NaN; },
    (x: any) => { x.dynamic_windowing = 'true'; },
    (x: any) => { x.max_grid_cells = 1_000_001; },
    (x: any) => { x.regional_example_request.goal.longitude = 100; },
  ]) {
    const invalid = structuredClone(body); mutate(invalid.regions[0].planning);
    assert.throws(() => decodePlanningRegion(invalid));
  }
});
