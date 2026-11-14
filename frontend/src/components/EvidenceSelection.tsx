import type { SelectedEvidence } from "../map/evidenceOverlays.ts";
import { JEZERO_EVIDENCE_DEMO } from "../fixtures/jezeroEvidenceDemo.ts";

export default function EvidenceSelection({ selection }: { selection: SelectedEvidence | null }) {
  return <section className="evidence-selection" aria-labelledby="evidence-selection-title">
    <h2 id="evidence-selection-title">Overlay selection</h2>
    {!selection && <p>Enable a science or rover layer and select a marker to inspect this fixture record.</p>}
    {selection?.kind === "science" && <div>
      <strong>{selection.item.label}</strong>
      <p>{selection.item.category} · observed historical science context</p>
      <p>{selection.item.rationale}</p>
      <a href={selection.item.sourceUrl} target="_blank" rel="noreferrer">Source record ↗</a>
    </div>}
    {selection?.kind === "rover_stop" && <div>
      <strong>Perseverance stop {selection.item.recordId}</strong>
      <p>Sol {selection.item.sol} · observed historical rover position</p>
      {selection.item.observationUrl && <a href={selection.item.observationUrl} target="_blank" rel="noreferrer">Source-provided observation reference ↗</a>}
    </div>}
    <p className="notice">{JEZERO_EVIDENCE_DEMO.provenance.limitations[1]}</p>
  </section>;
}
