import type { SpecialistTrace as Trace } from "../types/routeMetadata.ts";
import {domainName,readableText} from '../services/domainNames.ts';
const application = { terrain_cost: "Terrain cost and coverage checks", context_only: "Context only", dose_scenario: "Dose scenario only", none: "No evidence applied" };
export default function SpecialistTrace({ traces }: { traces: Trace[] }) {
  if (!traces.length) return null;
  return <details className="specialist-trace"><summary>Specialist selection and execution</summary>
    <p>Review which specialist analyses were selected, completed and applied. Surface obstacle context is included in terrain analysis.</p>
    {traces.map(trace => <article key={trace.agent_id}><h4>{domainName(trace.agent_id,trace.public_name)}</h4>
      <p>{trace.required ? "Required" : "Optional"} · {trace.selected ? "Selected" : "Skipped"} · execution: {trace.execution_state} · data quality: {trace.result_status ?? "No result"} ({trace.data_kind})</p>
      <p>{readableText(trace.selection_reason)}</p><p>Application: {application[trace.application]}</p>
      {trace.application === "dose_scenario" && <p>Scenario constraint: {trace.constraint_status}</p>}
      <ul>{trace.limitations.map((text,i) => <li key={i}>{readableText(text)}</li>)}</ul>
      {trace.artifact_id && <small>Supporting evidence recorded.</small>}
    </article>)}
  </details>;
}
