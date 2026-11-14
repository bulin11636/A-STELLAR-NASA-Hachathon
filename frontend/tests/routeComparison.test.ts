import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { compareRoutes } from "../src/services/routeComparison.ts";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/computed-route.json",import.meta.url),"utf8"));

test("revision comparison uses measured deltas and complete ordered stops", () => {
  const child = structuredClone(fixture);
  child.metadata.parent_route_id = fixture.result.route_id;
  child.result.metrics.distance_m += 120;
  child.metadata.planner.objective_cost += 120;
  child.metadata.request.waypoints = [fixture.result.route[1],fixture.result.route[2]];
  const comparison = compareRoutes(fixture,child);
  assert.equal(comparison.distanceDelta,120);
  assert.equal(comparison.objectiveDelta,120);
  assert.equal(comparison.added,2);
  assert.equal(comparison.orderChanged,true);
});

test("different objectives or resolutions do not receive misleading cost deltas", () => {
  const child = structuredClone(fixture);
  child.metadata.parent_route_id = fixture.result.route_id;
  child.metadata.request.mode = 'safest';
  assert.equal(compareRoutes(fixture,child).objectiveDelta,null);
  child.metadata.request.mode = fixture.metadata.request.mode;
  child.metadata.grid.planning_resolution_m[0] *= 2;
  assert.equal(compareRoutes(fixture,child).objectiveDelta,null);
  child.metadata.scope.dataset_version = 'different';
  assert.equal(compareRoutes(fixture,child).distanceDelta,null);
  child.metadata.parent_route_id = 'wrong';
  assert.throws(() => compareRoutes(fixture,child));
});

test("added visits to an existing location are counted individually", () => {
  const parent = structuredClone(fixture), child = structuredClone(fixture);
  const a = fixture.result.route[1], b = fixture.result.route[2];
  parent.metadata.request.waypoints = [a,b];
  child.metadata.parent_route_id = parent.result.route_id;
  child.metadata.request.waypoints = [a,b,a];
  assert.equal(compareRoutes(parent,child).added,1);
});
