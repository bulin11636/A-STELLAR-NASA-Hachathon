import assert from "node:assert/strict";
import test from "node:test";
import { JEZERO_EVIDENCE_DEMO } from "../src/fixtures/jezeroEvidenceDemo.ts";
import { evidenceAtPoint, marsSphereDistanceM } from "../src/services/evidenceAtPoint.ts";

test("Mars-sphere distance is symmetric, seam-aware, and zero at an identical point", () => {
  const point = { longitude: 77.4509, latitude: 18.4446 };
  assert.equal(marsSphereDistanceM(point, point), 0);
  assert.equal(marsSphereDistanceM(point, { longitude: 77.451, latitude: 18.445 }), marsSphereDistanceM({ longitude: 77.451, latitude: 18.445 }, point));
  assert(marsSphereDistanceM({ longitude: 359.9, latitude: 0 }, { longitude: 0.1, latitude: 0 }) < 20_000);
});

test("evidence-at-point reports nearest fixture records and explicit unknowns", () => {
  const stop = JEZERO_EVIDENCE_DEMO.roverStops[0];
  const result = evidenceAtPoint(stop);
  assert.equal(result.nearestRoverStop?.item.recordId, stop.recordId);
  assert.equal(result.nearestRoverStop?.distance_m, 0);
  assert.ok(result.nearestScience);
  assert.match(result.warnings.join(" "), /unvalidated/);
});
