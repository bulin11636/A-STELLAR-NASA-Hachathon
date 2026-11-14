import assert from "node:assert/strict";
import test from "node:test";
import { EVIDENCE_LAYERS, canToggleLayer, stateLabel } from "../src/map/layerRegistry.ts";

test("layer registry preserves explicit evidence states and provenance", () => {
  assert.deepEqual(EVIDENCE_LAYERS.map((layer) => layer.state), [
    "observed", "prototype", "observed", "observed", "observed", "scenario", "unavailable",
  ]);
  for (const layer of EVIDENCE_LAYERS) {
    assert.ok(layer.provenance.sourceName);
    assert.ok(layer.provenance.sourceUrl.startsWith("https://"));
    assert.ok(layer.provenance.limitations.length > 0);
  }
});

test("only browser-ready layers can be toggled", () => {
  const basemap = EVIDENCE_LAYERS.find((layer) => layer.id === "mars_basemap");
  const sciencePois = EVIDENCE_LAYERS.find((layer) => layer.id === "science_pois");
  const thermal = EVIDENCE_LAYERS.find((layer) => layer.id === "thermal");
  assert.ok(basemap && sciencePois && thermal);
  assert.equal(canToggleLayer(basemap), true);
  assert.equal(canToggleLayer(sciencePois), true);
  assert.equal(canToggleLayer(thermal), false);
  assert.equal(stateLabel("unavailable"), "Unavailable");
});
