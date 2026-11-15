import type { LayerDisplayState } from "./LayerPanel.tsx";
import type { LocationEvidence } from "../services/evidenceAtPoint.ts";
import { buildMissionBriefing, downloadMissionBriefing } from "../services/missionBriefing.ts";
import type { MarsCoordinate, PlanRouteResponse } from "../types/api.ts";
import type { RouteAssessment } from "../types/routeMetadata.ts";

import { percentScore } from '../services/assessmentDisplay.ts';

export default function MissionBriefing({ objective, onObjectiveChange, start, goal, route, assessment, layers, evidence }: {
  objective: string;
  onObjectiveChange: (value: string) => void;
  start: MarsCoordinate | null;
  goal: MarsCoordinate | null;
  route: PlanRouteResponse | null;
  assessment: RouteAssessment | null;
  layers: Readonly<Record<string, LayerDisplayState>>;
  evidence: LocationEvidence | null;
}) {
  const activeLayerCount = Object.values(layers).filter((layer) => layer.visible).length;
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
      <dt>Start / goal</dt><dd>{start && goal ? "Selected on map" : "Incomplete"}</dd>
      <dt>Route</dt><dd>{route ? route.source + " · " + route.route_id : "Not requested"}</dd>
      <dt>Distance</dt><dd>{route?.metrics.distance_m == null ? "Not assessed" : `${route.metrics.distance_m.toFixed(1)} m`}</dd>
      <dt>Estimated time</dt><dd>{route?.metrics.estimated_time_min == null ? "Not estimated" : `${route.metrics.estimated_time_min.toFixed(1)} min`}</dd>
      <dt>Mission gate</dt><dd>{assessment?.hard_gate_status ?? "Unassessed"}</dd>
      <dt>Risk / confidence</dt><dd>{assessment ? `${percentScore(assessment.risk_score)} / ${percentScore(assessment.assessment_confidence)}` : "Not assessed"}</dd>
      <dt>Visible layers</dt><dd>{activeLayerCount}</dd>
      <dt>Evidence point</dt><dd>{evidence ? "Selected; fixture-scoped context only" : "Not selected"}</dd>
    </dl>
    {assessment?.time && <details><summary>Walking time assumptions</summary><ul>{assessment.time.assumptions.map((text,i)=><li key={i}>{text}</li>)}</ul></details>}
    {assessment && <section aria-label="Route advisories"><h3>Route advisories</h3>
      <ul>{assessment.risk_factors.map((factor) => <li key={factor.agent_id}><strong>{factor.public_name || factor.agent_id}</strong>: {factor.message} ({factor.status})</li>)}</ul>
    </section>}
    <p>Exports null metrics and unknowns as shown; it does not infer route quality or astronaut safety.</p>
    <button type="button" onClick={exportBriefing}>Export briefing JSON</button>
  </section>;
}
