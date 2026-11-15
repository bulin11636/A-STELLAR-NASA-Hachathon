import assert from "node:assert/strict";
import test from "node:test";
import { buildMissionBriefing } from "../src/services/missionBriefing.ts";
import { COORDINATE_SYSTEM, type PlanRouteResponse } from "../src/types/api.ts";
import type { RouteAssessment } from "../src/types/routeMetadata.ts";

const route: PlanRouteResponse = {
  status: "success", route_id: "demo-jezero-1", region_id: "jezero", coordinate_system: COORDINATE_SYSTEM,
  mode: "safest", source: "mock", route: [{ longitude: 77.42, latitude: 18.44 }, { longitude: 77.48, latitude: 18.46 }],
  metrics: { distance_m: null, estimated_time_min: null, risk_score: null }, warnings: ["Demonstration route only."],
};
const assessment: RouteAssessment = {
  schema_version:"2",score_scale:"0..100",formula_version:"relative-terrain-scenario-v2",gate_reasons:[],
  time: null, radiation_duration_min: null, radiation_duration_basis: "unavailable", dose_estimate_usv: null, dose_uncertainty_usv: null,
  radiation_constraint_status: "unknown", required_unassessed: ["A3"], required_failed: [], mission_profile: null,
  hard_gate_status: "unassessed", risk_score: null, assessment_confidence: 40,
  risk_factors: [{ agent_id: "A3", kind: "context", status: "unassessed", risk_score: null, public_name:"Radiation Exposure and Mission Dose Assessment Agent",model_version:null,evidence:null,component_reasons:{},confidence_contribution:0,risk_contribution:null,
    evidence_quality: { availability: 0, route_coverage: 0, temporal_applicability: 0, validation_provenance: 0 }, evidence_ids: [], message: "No radiation scenario is available." }],
  limitations: ["Risk is not assessed."],
};

test("mission briefing preserves mock route nulls and selected layer provenance", () => {
  const briefing = buildMissionBriefing({
    generatedAt: "2026-11-14T00:00:00Z", objective: "Inspect evidence", start: route.route[0], goal: route.route[1], route,
    assessment: null, activeLayers: { mars_basemap: { visible: true, opacity: 1 } }, evidenceAtPoint: null,
  });
  assert.equal(briefing.status, "demonstration_not_safety_validated");
  assert.deepEqual(briefing.route.metrics, route.metrics);
  assert.equal(briefing.enabled_layers.length, 1);
  assert.equal(briefing.enabled_layers[0].id, "mars_basemap");
  assert.match(briefing.limitations.join(" "), /No terrain/);
});

test("mission briefing exports backend-owned assessment provenance", () => {
  const briefing = buildMissionBriefing({
    generatedAt: "2026-11-14T00:00:00Z", objective: "Assess route", start: route.route[0], goal: route.route[1], route, assessment,
    activeLayers: {}, evidenceAtPoint: null,
  });
  assert.equal(briefing.assessment?.hard_gate_status, "unassessed");
  assert.equal(briefing.assessment?.assessment_confidence, 40);
  assert.equal(briefing.assessment?.factors[0].message, "No radiation scenario is available.");
});

test("mission briefing records a missing route as unknown null metrics", () => {
  const briefing = buildMissionBriefing({
    generatedAt: "2026-11-14T00:00:00Z", objective: "", start: null, goal: null, route: null, assessment: null, activeLayers: {}, evidenceAtPoint: null,
  });
  assert.equal(briefing.objective, null);
  assert.equal(briefing.route.route_id, null);
  assert.equal(briefing.route.metrics.distance_m, null);
});
