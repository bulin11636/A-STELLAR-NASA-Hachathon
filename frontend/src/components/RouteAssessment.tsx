import type { RouteAssessment as Assessment } from "../types/routeMetadata.ts";

function percent(value: number | null | undefined) {
  return value == null ? "Not assessed" : `${Math.round(value * 100)}%`;
}

function gateLabel(status: Assessment["hard_gate_status"]) {
  if (status === "pass") return "Pass";
  if (status === "blocked") return "Blocked";
  return "Unassessed";
}

export default function RouteAssessment({ assessment }: { assessment: Assessment | null }) {
  if (!assessment) return null;
  return <section aria-label="Walking time and exposure assessment"><h3>Walking time and exposure assumptions</h3>
    {assessment.time ? <><p>Walking speed: {assessment.time.speed_m_s} m/s · travel: {assessment.time.travel_min.toFixed(1)} min · intermediate dwell: {assessment.time.stop_min.toFixed(1)} min · total: {assessment.time.total_min.toFixed(1)} min.</p>
      <ul>{assessment.time.assumptions.map((text,i) => <li key={i}>{text}</li>)}</ul></> : <p>Time is not estimated. Supply an assumed walking speed in Advanced mode.</p>}
    <p>Radiation duration: {assessment.radiation_duration_min?.toFixed(1) ?? "Unknown"} min ({assessment.radiation_duration_basis}). Dose scenario: {assessment.dose_estimate_usv?.toFixed(3) ?? "Not assessed"} µSv · scenario constraint: {assessment.radiation_constraint_status}.</p>
    {!!assessment.required_unassessed.length && <p role="alert">Required analyses remain unassessed. This is a provisional terrain route; inspect the specialist trace.</p>}
    {!!assessment.required_failed.length && <p role="alert">Required scenario checks failed. This route does not meet those scenario requirements.</p>}
    <section aria-label="Mission risk assessment"><h3>Mission risk assessment</h3>
      <dl>
        <dt>Hard safety gate</dt><dd>{gateLabel(assessment.hard_gate_status)}</dd>
        <dt>Composite risk</dt><dd>{percent(assessment.risk_score)}</dd>
        <dt>Assessment confidence</dt><dd>{percent(assessment.assessment_confidence)}</dd>
        <dt>Mission profile</dt><dd>{assessment.mission_profile ? `${assessment.mission_profile.profile_id.replace("_", " ")} (${assessment.mission_profile.version})` : "Not recorded"}</dd>
      </dl>
      {assessment.risk_score == null && <p>Composite risk is withheld until calibrated specialist risk inputs are available. Confidence reflects the completeness and applicability of available evidence, not EVA safety certification.</p>}
      {!!assessment.risk_factors.length && <ul aria-label="Risk factors">{assessment.risk_factors.map(factor => <li key={factor.agent_id}>
        <strong>{factor.agent_id}</strong>: {factor.message} Status: {factor.status}; risk: {percent(factor.risk_score)}; evidence quality: {percent((factor.evidence_quality.availability + factor.evidence_quality.route_coverage + factor.evidence_quality.temporal_applicability + factor.evidence_quality.validation_provenance) / 4)}.
        {assessment.mission_profile?.risk_weights[factor.agent_id] != null && ` Profile weight: ${percent(assessment.mission_profile.risk_weights[factor.agent_id])}.`}
      </li>)}</ul>}
    </section>
    <ul>{assessment.limitations.map((text,i) => <li key={i}>{text}</li>)}</ul>
  </section>;
}
