import type { RouteAssessment as Assessment } from "../types/routeMetadata.ts";
export default function RouteAssessment({ assessment }: { assessment: Assessment | null }) {
  if (!assessment) return null;
  return <section aria-label="Walking time and exposure assessment"><h3>Walking time and exposure assumptions</h3>
    {assessment.time ? <><p>Walking speed: {assessment.time.speed_m_s} m/s · travel: {assessment.time.travel_min.toFixed(1)} min · intermediate dwell: {assessment.time.stop_min.toFixed(1)} min · total: {assessment.time.total_min.toFixed(1)} min.</p>
      <ul>{assessment.time.assumptions.map((text,i) => <li key={i}>{text}</li>)}</ul></> : <p>Time is not estimated. Supply an assumed walking speed in Advanced mode.</p>}
    <p>Radiation duration: {assessment.radiation_duration_min?.toFixed(1) ?? "Unknown"} min ({assessment.radiation_duration_basis}). Dose scenario: {assessment.dose_estimate_usv?.toFixed(3) ?? "Not assessed"} µSv · scenario constraint: {assessment.radiation_constraint_status}.</p>
    {!!assessment.required_unassessed.length && <p role="alert">Required analyses remain unassessed. This is a provisional terrain route; inspect the specialist trace.</p>}
    {!!assessment.required_failed.length && <p role="alert">Required scenario checks failed. This route does not meet those scenario requirements.</p>}
    <ul>{assessment.limitations.map((text,i) => <li key={i}>{text}</li>)}</ul>
  </section>;
}
