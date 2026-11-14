import type { LayerDisplayState } from "./LayerPanel.tsx";
import type { LocationEvidence } from "../services/evidenceAtPoint.ts";
import { buildMissionBriefing, downloadMissionBriefing } from "../services/missionBriefing.ts";
import type { MarsCoordinate, PlanRouteResponse } from "../types/api.ts";

export default function MissionBriefing({ objective, onObjectiveChange, start, goal, route, layers, evidence }: {
  objective: string;
  onObjectiveChange: (value: string) => void;
  start: MarsCoordinate | null;
  goal: MarsCoordinate | null;
  route: PlanRouteResponse | null;
  layers: Readonly<Record<string, LayerDisplayState>>;
  evidence: LocationEvidence | null;
}) {
  const activeLayerCount = Object.values(layers).filter((layer) => layer.visible).length;
  const exportBriefing = () => downloadMissionBriefing(buildMissionBriefing({
    generatedAt: new Date().toISOString(), objective, start, goal, route, activeLayers: layers, evidenceAtPoint: evidence,
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
      <dt>Visible layers</dt><dd>{activeLayerCount}</dd>
      <dt>Evidence point</dt><dd>{evidence ? "Selected; fixture-scoped context only" : "Not selected"}</dd>
    </dl>
    <p>Exports null metrics and unknowns as shown; it does not infer route quality or astronaut safety.</p>
    <button type="button" onClick={exportBriefing}>Export briefing JSON</button>
  </section>;
}
