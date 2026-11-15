import type { SpecialistTrace as Trace } from "../types/routeMetadata.ts";
const application = { terrain_cost: "Terrain cost and coverage checks", context_only: "Context only", dose_scenario: "Dose scenario only", none: "No evidence applied" };
export default function SpecialistTrace({ traces }: { traces: Trace[] }) {
  if (!traces.length) return null;
  return <details className="specialist-trace"><summary>Specialist selection and execution</summary>
    <p>Selection, execution and data quality are separate. A5 surface context is merged into the Surface Traversability and Terrain Hazard Agent.</p>
    {traces.map(trace => <article key={trace.agent_id}><h4>{trace.public_name}</h4>
      <p>{trace.required ? "Required" : "Optional"} · {trace.selected ? "Selected" : "Skipped"} · execution: {trace.execution_state} · data quality: {trace.result_status ?? "No result"} ({trace.data_kind})</p>
      <p>{trace.selection_reason}</p><p>Application: {application[trace.application]}</p>
      {trace.application === "dose_scenario" && <p>Scenario constraint: {trace.constraint_status}</p>}
      <ul>{trace.limitations.map((text,i) => <li key={i}>{text}</li>)}</ul>
      {trace.artifact_id && <small>Evidence reference: {trace.artifact_id}</small>}
    </article>)}
  </details>;
}
