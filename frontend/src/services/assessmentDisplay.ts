// Presentation conversions only; all quality, risk and confidence calculations stay on the backend.
export function percentScore(value: number | null | undefined) {
  return value == null ? 'Not assessed' : `${Number(value.toFixed(1))}%`;
}
export function unitFraction(value: number | null | undefined) {
  return percentScore(value == null ? value : value*100);
}
