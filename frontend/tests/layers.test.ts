import assert from "node:assert/strict";
import test from "node:test";
import { EVIDENCE_LAYERS, LAYER_GROUPS, canToggleLayer, stateLabel } from "../src/map/layerRegistry.ts";

test("layer registry preserves explicit evidence states and provenance", () => {
  assert.equal(new Set(EVIDENCE_LAYERS.map(layer=>layer.id)).size,EVIDENCE_LAYERS.length);
  assert.deepEqual(LAYER_GROUPS.slice(1,6).map(group=>group.label.slice(0,2)),['A1','A2','A3','A4','A6']);
  assert.deepEqual(EVIDENCE_LAYERS.map(layer=>layer.id),LAYER_GROUPS.flatMap(group=>[...group.ids]));
  assert.equal(EVIDENCE_LAYERS.find(layer=>layer.id==='radiation')?.state,'scenario');
  for (const layer of EVIDENCE_LAYERS) {
    assert.ok(layer.provenance.sourceName);
    assert.ok(layer.provenance.sourceUrl.startsWith("https://"));
    assert.ok(layer.provenance.limitations.length > 0);
  }
});

test("only browser-ready layers can be toggled", () => {
  const basemap = EVIDENCE_LAYERS.find((layer) => layer.id === "mars_basemap");
  const jezeroImagery = EVIDENCE_LAYERS.find((layer) => layer.id === "jezero_imagery");
  const sciencePois = EVIDENCE_LAYERS.find((layer) => layer.id === "science_pois");
  const thermal = EVIDENCE_LAYERS.find((layer) => layer.id === "thermal");
  assert.ok(basemap && jezeroImagery && sciencePois && thermal);
  assert.equal(canToggleLayer(basemap), true);
  assert.equal(canToggleLayer(jezeroImagery), true);
  assert.equal(canToggleLayer(sciencePois), true);
  assert.equal(canToggleLayer(thermal), false);
  assert.equal(stateLabel("unavailable"), "Unavailable");
});
