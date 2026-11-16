import type { LayerDisplayState } from "./LayerPanel.tsx";
import type { LocationEvidence } from "../services/evidenceAtPoint.ts";
import { buildMissionBriefing, downloadMissionBriefing } from "../services/missionBriefing.ts";
import type { MarsCoordinate, PlanRouteResponse } from "../types/api.ts";
import type { RouteAssessment, RouteMetadata } from "../types/routeMetadata.ts";

import { percentScore } from '../services/assessmentDisplay.ts';
import { displayWarning } from '../services/displayWarnings.ts';

export default function MissionBriefing({ objective, onObjectiveChange, start, goal, route, assessment, metadata, layers, evidence }: {
  objective: string;
  onObjectiveChange: (value: string) => void;
  start: MarsCoordinate | null;
  goal: MarsCoordinate | null;
  route: PlanRouteResponse | null;
  assessment: RouteAssessment | null;
  metadata: RouteMetadata | null;
  layers: Readonly<Record<string, LayerDisplayState>>;
  evidence: LocationEvidence | null;
}) {
  const activeLayerCount = Object.values(layers).filter((layer) => layer.visible).length;
  const knownConditions = assessment?.risk_factors.filter((factor) => factor.status === "assessed" || factor.status === "contextual") ?? [];
  const attentionAreas = assessment?.risk_factors.filter((factor) => !["assessed", "contextual", "not_applicable"].includes(factor.status)) ?? [];
  const limitations = [...new Set([...(assessment?.limitations ?? []), ...(route?.warnings ?? [])].map(displayWarning))];
  const exportBriefing = () => downloadMissionBriefing(buildMissionBriefing({
    generatedAt: new Date().toISOString(), objective, start, goal, route, assessment, activeLayers: layers, evidenceAtPoint: evidence,
  }));
  return <section className="mission-briefing" aria-labelledby="mission-briefing-title">
    <div className="info-heading"><h2 id="mission-briefing-title">Mission briefing</h2><span className="badge">F5</span></div>
    <strong className="mock-badge">DEMONSTRATION / NOT SAFETY-VALIDATED</strong>
    <label className="objective-label">Objective
      <textarea value={objective} rows={3} maxLength={500} onChange={(event) => onObjectiveChange(event.target.value)}
        aria-label="Mission objective" />
    </label>
    <dl className="briefing-summary">
      <dt>Start / goal</dt><dd>{start && goal ? `${start.longitude.toFixed(6)}, ${start.latitude.toFixed(6)} → ${goal.longitude.toFixed(6)}, ${goal.latitude.toFixed(6)}` : "Incomplete"}</dd>
      <dt>Route</dt><dd>{route ? route.source + " · " + route.route_id : "Not requested"}</dd>
      <dt>Distance</dt><dd>{route?.metrics.distance_m == null ? "Not assessed" : `${route.metrics.distance_m.toFixed(1)} m`}</dd>
      <dt>Estimated time</dt><dd>{route?.metrics.estimated_time_min == null ? "Not estimated" : `${route.metrics.estimated_time_min.toFixed(1)} min`}</dd>
      <dt>Mission gate</dt><dd>{assessment?.hard_gate_status ?? "Unassessed"}</dd>
      <dt>Risk / confidence</dt><dd>{assessment ? `${percentScore(assessment.risk_score)} / ${percentScore(assessment.assessment_confidence)}` : "Not assessed"}</dd>
      <dt>Visible layers</dt><dd>{activeLayerCount}</dd>
      <dt>Evidence point</dt><dd>{evidence ? "Selected; fixture-scoped context only" : "Not selected"}</dd>
    </dl>
    <section className="briefing-section" aria-labelledby="known-conditions-title"><h3 id="known-conditions-title">Known conditions</h3>
      {knownConditions.length ? <ul>{knownConditions.map((factor) => <li key={factor.agent_id}><strong>{factor.public_name || factor.agent_id}</strong>: {factor.message}</li>)}</ul>
        : <p>No route conditions have been assessed or supplied as contextual evidence.</p>}
    </section>
    <section className="briefing-section" aria-labelledby="attention-areas-title"><h3 id="attention-areas-title">Attention areas</h3>
      {assessment?.hard_gate_status && assessment.hard_gate_status !== "pass" && <p className="notice">Mission gate: {assessment.hard_gate_status}. Normal risk comparison is not available.</p>}
      {attentionAreas.length ? <ul>{attentionAreas.map((factor) => <li key={factor.agent_id}><strong>{factor.public_name || factor.agent_id}</strong>: {factor.message} ({factor.status})</li>)}</ul>
        : <p>No additional unassessed or incompatible route factors were reported.</p>}
    </section>
    <section className="briefing-section" aria-labelledby="limitations-title"><h3 id="limitations-title">Limitations</h3>
      {limitations.length ? <ul>{limitations.map((limitation, index) => <li key={`${limitation}-${index}`}>{limitation}</li>)}</ul>
        : <p>No additional limitations were supplied by the route record.</p>}
    </section>
    <details className="briefing-technical"><summary>Technical details</summary>
      {assessment?.time && <><h3>Walking time assumptions</h3><ul>{assessment.time.assumptions.map((text,i)=><li key={i}>{text}</li>)}</ul></>}
      {metadata && <dl className="briefing-summary">
        <dt>Mission profile</dt><dd>{metadata.planning_policy ? `${metadata.planning_policy.mission_profile_id} (${metadata.planning_policy.mission_profile_version})` : "Legacy / not selected"}</dd>
        <dt>Actual cell size</dt><dd>{metadata.planning_policy?.actual_cell_size_m.join(" × ") ?? metadata.grid.planning_resolution_m.join(" × ")} m</dd>
        <dt>Grid cells</dt><dd>{(metadata.grid.width * metadata.grid.height).toLocaleString()}</dd>
        <dt>Map alignment</dt><dd>{metadata.validation.map_alignment}</dd>
      </dl>}
    </details>
    <p>Exports null metrics and unknowns as shown; it does not infer route quality or astronaut safety.</p>
    <button type="button" onClick={exportBriefing}>Export briefing JSON</button>
  </section>;
}
