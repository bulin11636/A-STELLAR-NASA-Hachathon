import assert from "node:assert/strict";
import test from "node:test";
import { buildMissionBriefing } from "../src/services/missionBriefing.ts";
import { COORDINATE_SYSTEM, type PlanRouteResponse } from "../src/types/api.ts";

const route: PlanRouteResponse = {
  status: "success", route_id: "demo-jezero-1", region_id: "jezero", coordinate_system: COORDINATE_SYSTEM,
  mode: "safest", source: "mock", route: [{ longitude: 77.42, latitude: 18.44 }, { longitude: 77.48, latitude: 18.46 }],
  metrics: { distance_m: null, estimated_time_min: null, risk_score: null }, warnings: ["Demonstration route only."],
};

test("mission briefing preserves mock route nulls and selected layer provenance", () => {
  const briefing = buildMissionBriefing({
    generatedAt: "2026-11-14T00:00:00Z", objective: "Inspect evidence", start: route.route[0], goal: route.route[1], route,
    activeLayers: { mars_basemap: { visible: true, opacity: 1 } }, evidenceAtPoint: null,
  });
  assert.equal(briefing.status, "demonstration_not_safety_validated");
  assert.deepEqual(briefing.route.metrics, route.metrics);
  assert.equal(briefing.enabled_layers.length, 1);
  assert.equal(briefing.enabled_layers[0].id, "mars_basemap");
  assert.match(briefing.limitations.join(" "), /No terrain/);
});

test("mission briefing records a missing route as unknown null metrics", () => {
  const briefing = buildMissionBriefing({
    generatedAt: "2026-11-14T00:00:00Z", objective: "", start: null, goal: null, route: null, activeLayers: {}, evidenceAtPoint: null,
  });
  assert.equal(briefing.objective, null);
  assert.equal(briefing.route.route_id, null);
  assert.equal(briefing.route.metrics.distance_m, null);
});
