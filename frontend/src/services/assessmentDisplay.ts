// Presentation conversions only; all quality, risk and confidence calculations stay on the backend.
import type {RouteAssessment} from '../types/routeMetadata.ts';
export function riskDisplay(assessment:RouteAssessment | null | undefined) {
  const score=assessment?.risk_score ?? assessment?.partial_risk_score;
  if (score==null) return 'Not assessed';
  return `${Number(score.toFixed(1))} / 100${assessment?.risk_score==null ? ' (partial)' : ''}`;
}
export function percentScore(value: number | null | undefined) {
  return value == null ? 'Not assessed' : `${Number(value.toFixed(1))}%`;
}
export function unitFraction(value: number | null | undefined) {
  return percentScore(value == null ? value : value*100);
}
