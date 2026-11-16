import { EVIDENCE_LAYERS } from "../map/layerRegistry.ts";
import type { LayerDisplayState } from "../components/LayerPanel.tsx";
import type { LocationEvidence } from "./evidenceAtPoint.ts";
import type { MarsCoordinate, PlanRouteResponse } from "../types/api.ts";
import type { RouteAssessment } from "../types/routeMetadata.ts";
import { displayWarning } from './displayWarnings.ts';

export interface MissionBriefingInput {
  generatedAt: string;
  objective: string;
  start: MarsCoordinate | null;
  goal: MarsCoordinate | null;
  route: PlanRouteResponse | null;
  assessment: RouteAssessment | null;
  activeLayers: Readonly<Record<string, LayerDisplayState>>;
  evidenceAtPoint: LocationEvidence | null;
}

export function buildMissionBriefing(input: MissionBriefingInput) {
  const enabledLayers = EVIDENCE_LAYERS
    .filter((layer) => input.activeLayers[layer.id]?.visible)
    .map((layer) => ({
      id: layer.id,
      label: layer.label,
      evidence_state: layer.state,
      validation_status: layer.validationStatus,
      provenance: layer.provenance,
    }));
  return {
    format_version: "1",
    generated_at: input.generatedAt,
    status: input.route?.source === "mock" ? "demonstration_not_safety_validated" : input.route ? 'computed_route_available' : "incomplete",
    assessment_status: input.assessment?.hard_gate_status ?? 'unassessed',
    coordinate_system: "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
    objective: input.objective.trim() || null,
    selections: { start: input.start, goal: input.goal },
    route: input.route ? {
      route_id: input.route.route_id,
      source: input.route.source,
      mode: input.route.mode,
      vertices: input.route.route,
      metrics: input.route.metrics,
      warnings: input.route.warnings.map(displayWarning),
    } : {
      route_id: null,
      source: null,
      mode: null,
      vertices: [],
      metrics: { distance_m: null, estimated_time_min: null, risk_score: null },
      warnings: ["No route has been requested."],
    },
    assessment: input.assessment ? {
      schema_version: input.assessment.schema_version, score_scale: input.assessment.score_scale,
      formula_version: input.assessment.formula_version, gate_reasons: input.assessment.gate_reasons, time: input.assessment.time,
      hard_gate_status: input.assessment.hard_gate_status,
      risk_score: input.assessment.risk_score,
      assessment_confidence: input.assessment.assessment_confidence,
      mission_profile: input.assessment.mission_profile,
      factors: input.assessment.risk_factors.map((factor) => ({
        agent_id: factor.agent_id, public_name: factor.public_name, kind: factor.kind, status: factor.status, risk_score: factor.risk_score,
        model_version: factor.model_version, confidence_contribution: factor.confidence_contribution, risk_contribution: factor.risk_contribution,
        evidence: factor.evidence, component_reasons: factor.component_reasons,
        evidence_quality: factor.evidence_quality, evidence_ids: factor.evidence_ids, message: factor.message,
      })),
      limitations: input.assessment.limitations,
    } : null,
    enabled_layers: enabledLayers,
    evidence_at_selected_point: input.evidenceAtPoint ? {
      point: input.evidenceAtPoint.point,
      nearest_science_fixture: input.evidenceAtPoint.nearestScience && {
        id: input.evidenceAtPoint.nearestScience.item.id,
        label: input.evidenceAtPoint.nearestScience.item.label,
        distance_m: input.evidenceAtPoint.nearestScience.distance_m,
        source_url: input.evidenceAtPoint.nearestScience.item.sourceUrl,
      },
      nearest_rover_fixture: input.evidenceAtPoint.nearestRoverStop && {
        record_id: input.evidenceAtPoint.nearestRoverStop.item.recordId,
        sol: input.evidenceAtPoint.nearestRoverStop.item.sol,
        distance_m: input.evidenceAtPoint.nearestRoverStop.distance_m,
        source_url: input.evidenceAtPoint.nearestRoverStop.item.sourceUrl,
        observation_url: input.evidenceAtPoint.nearestRoverStop.item.observationUrl,
      },
      warnings: input.evidenceAtPoint.warnings,
    } : null,
    limitations: [
      input.route?.source==='computed' ? 'Computed terrain route; additional environmental assessment may be incomplete.' : "Demonstration interface only. No terrain, thermal, or astronaut-safety validation is represented.",
      "WMTS, wire-coordinate, and DEM alignment remain unvalidated.",
      "Enabled fixture layers are small selected subsets, not complete mission coverage.",
    ],
  };
}

export function downloadMissionBriefing(briefing: ReturnType<typeof buildMissionBriefing>) {
  const payload = new Blob([JSON.stringify(briefing, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(payload);
  const link = document.createElement("a");
  link.href = url;
  link.download = "a-stellar-jezero-mission-briefing.json";
  link.click();
  URL.revokeObjectURL(url);
}
