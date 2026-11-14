import type { LocationEvidence } from "../services/evidenceAtPoint.ts";

function coordinate(value: number) {
  return value.toFixed(6) + "°";
}

function distance(value: number) {
  return value >= 1_000 ? (value / 1_000).toFixed(2) + " km" : Math.round(value) + " m";
}

export default function EvidenceDrawer({ evidence }: { evidence: LocationEvidence | null }) {
  return <section className="evidence-drawer" aria-labelledby="evidence-drawer-title">
    <div className="info-heading"><h2 id="evidence-drawer-title">Evidence at point</h2><span className="badge">F4</span></div>
    {!evidence && <p>Select any in-coverage map point to inspect the available fixture evidence and unknowns.</p>}
    {evidence && <div>
      <p className="point-coordinate">Selected: {coordinate(evidence.point.longitude)} E · {coordinate(evidence.point.latitude)} demo latitude</p>
      <dl className="point-evidence">
        <dt>Nearest science POI</dt>
        <dd>{evidence.nearestScience ? <><strong>{evidence.nearestScience.item.label}</strong> · {distance(evidence.nearestScience.distance_m)} among this fixture<br />
          <a href={evidence.nearestScience.item.sourceUrl} target="_blank" rel="noreferrer">Source record ↗</a></> : "Unknown"}</dd>
        <dt>Nearest rover context</dt>
        <dd>{evidence.nearestRoverStop ? <><strong>Stop {evidence.nearestRoverStop.item.recordId}</strong> · Sol {evidence.nearestRoverStop.item.sol} · {distance(evidence.nearestRoverStop.distance_m)} among this fixture<br />
          {evidence.nearestRoverStop.item.observationUrl && <a href={evidence.nearestRoverStop.item.observationUrl} target="_blank" rel="noreferrer">Source-provided observation reference ↗</a>}</> : "Unknown"}</dd>
        <dt>Geology polygon</dt><dd>Unavailable in the browser; the SIM 3464 polygon overlay is not published.</dd>
        <dt>Terrain / thermal</dt><dd>Unknown. No validated traversability or calibrated thermal constraint is available.</dd>
      </dl>
      <ul className="point-warnings">{evidence.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
    </div>}
  </section>;
}
