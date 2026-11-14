import assert from "node:assert/strict";
import test from "node:test";
import { JEZERO_EVIDENCE_DEMO } from "../src/fixtures/jezeroEvidenceDemo.ts";
import { COORDINATE_SYSTEM } from "../src/types/api.ts";

test("Jezero overlay fixture preserves its source metadata and wire coordinates", () => {
  assert.equal(JEZERO_EVIDENCE_DEMO.coordinateSystem, COORDINATE_SYSTEM);
  assert.equal(JEZERO_EVIDENCE_DEMO.evidenceState, "observed");
  assert.equal(JEZERO_EVIDENCE_DEMO.scienceSites.length, 4);
  assert.equal(JEZERO_EVIDENCE_DEMO.roverStops.length, 4);
  assert.equal(JEZERO_EVIDENCE_DEMO.traverse.length, 3);
  for (const point of [...JEZERO_EVIDENCE_DEMO.scienceSites, ...JEZERO_EVIDENCE_DEMO.roverStops]) {
    assert(point.longitude >= 0 && point.longitude < 360);
    assert(point.latitude >= -90 && point.latitude <= 90);
    assert.ok(point.sourceUrl.startsWith("https://"));
  }
  assert.match(JEZERO_EVIDENCE_DEMO.provenance.limitations.join(" "), /unvalidated/);
});
