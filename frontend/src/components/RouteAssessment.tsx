import type { RouteAssessment as Assessment } from "../types/routeMetadata.ts";

import { percentScore,unitFraction,riskDisplay } from '../services/assessmentDisplay.ts';
import {domainName,readableText} from '../services/domainNames.ts';

function gateLabel(status: Assessment["hard_gate_status"]) {
  if (status === "pass") return "Pass";
  if (status === "blocked") return "Blocked";
  return "Unassessed";
}

export default function RouteAssessment({ assessment }: { assessment: Assessment | null }) {
  if (!assessment) return null;
  return <section aria-label="Walking time and exposure assessment"><h3>Walking time and exposure assumptions</h3>
    {assessment.time ? <><p>Walking speed: {assessment.time.speed_m_s} m/s · travel: {assessment.time.travel_min.toFixed(1)} min · intermediate dwell: {assessment.time.stop_min.toFixed(1)} min · total: {assessment.time.total_min.toFixed(1)} min.</p>
      <ul>{assessment.time.assumptions.map((text,i) => <li key={i}>{readableText(text)}</li>)}</ul></> : <p>Time is not estimated. Supply an assumed walking speed in Advanced mode.</p>}
    <p>Radiation duration: {assessment.radiation_duration_min?.toFixed(1) ?? "Unknown"} min ({assessment.radiation_duration_basis}). Dose scenario: {assessment.dose_estimate_usv?.toFixed(3) ?? "Not assessed"} µSv · scenario constraint: {assessment.radiation_constraint_status}.</p>
    {!!assessment.required_unassessed.length && <p role="alert">Required analyses remain unassessed. This is a provisional terrain route; inspect the specialist trace.</p>}
    {!!assessment.required_failed.length && <p role="alert">Required scenario checks failed. This route does not meet those scenario requirements.</p>}
    <section aria-label="Mission risk assessment"><h3>Mission risk assessment</h3>
      <dl>
        <dt>Mission gate</dt><dd>{gateLabel(assessment.hard_gate_status)}</dd>
        <dt>Risk score</dt><dd>{riskDisplay(assessment)}</dd>
        {assessment.risk_evidence_coverage!=null && <><dt>Risk evidence coverage</dt><dd>{percentScore(assessment.risk_evidence_coverage)} of profile risk weight</dd></>}
        <dt>Assessment confidence</dt><dd>{percentScore(assessment.assessment_confidence)}</dd>
        <dt>Mission profile</dt><dd>{assessment.mission_profile ? `${assessment.mission_profile.profile_id.replace("_", " ")} (${assessment.mission_profile.version})` : "Not recorded"}</dd>
      </dl>
      {assessment.risk_score == null && <p>{assessment.partial_risk_score!=null ? 'Partial risk uses only assessed factors, with their weights normalized. Missing factors are not counted as zero; complete mission risk remains unavailable.' : 'No applicable risk factors have been assessed.'} Confidence describes evidence completeness; inspect the mission gate and missing factors.</p>}
      {assessment.gate_reasons.map((reason,i)=><p key={i}>{readableText(reason)}</p>)}
      {!!assessment.risk_factors.length && <ul aria-label="Risk factors">{assessment.risk_factors.map(factor => <li key={factor.agent_id}>
        <strong>{domainName(factor.agent_id,factor.public_name)}</strong>: {readableText(factor.message)} Status: {factor.status}; risk: {unitFraction(factor.risk_score)}; confidence contribution: {percentScore(factor.confidence_contribution)}.
        <span> Quality components — availability: {unitFraction(factor.evidence_quality.availability)}; route coverage: {unitFraction(factor.evidence_quality.route_coverage)}; time applicability: {unitFraction(factor.evidence_quality.temporal_applicability)}; validation/provenance: {unitFraction(factor.evidence_quality.validation_provenance)}.</span>
        {assessment.mission_profile?.risk_weights[factor.agent_id] != null && ` Profile weight: ${unitFraction(assessment.mission_profile.risk_weights[factor.agent_id])}.`}
      </li>)}</ul>}
    </section>
    <ul>{assessment.limitations.map((text,i) => <li key={i}>{readableText(text)}</li>)}</ul>
  </section>;
}
