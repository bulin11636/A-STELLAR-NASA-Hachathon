import assert from "node:assert/strict";
import test from "node:test";
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import LayerPanel from '../src/components/LayerPanel.tsx';
import { EVIDENCE_LAYERS, LAYER_GROUPS, canToggleLayer, stateLabel } from "../src/map/layerRegistry.ts";

test("layer registry preserves explicit evidence states and provenance", () => {
  assert.equal(new Set(EVIDENCE_LAYERS.map(layer=>layer.id)).size,EVIDENCE_LAYERS.length);
  assert.deepEqual(LAYER_GROUPS.slice(1,5).map(group=>group.label.slice(0,2)),['A1','A2','A4','A6']);
  assert.deepEqual(EVIDENCE_LAYERS.map(layer=>layer.id),LAYER_GROUPS.flatMap(group=>[...group.ids]));
  assert.equal(EVIDENCE_LAYERS.some(layer=>layer.id==='radiation'),false);
  for (const layer of EVIDENCE_LAYERS) {
    assert.ok(layer.provenance.sourceName);
    assert.ok(layer.provenance.sourceUrl.startsWith("https://"));
    assert.ok(layer.provenance.limitations.length > 0);
  }
});

test('unavailable layers and non-spatial scenarios do not appear as map controls',()=>{
  const props={layers:{},onLayerChange(){},availability:{geology:false,thermal:false,thermal_night:false}};
  const html=renderToStaticMarkup(createElement(LayerPanel,props));
  assert(!html.includes('Radiation'));
  assert(!html.includes('Show SIM 3464 geology'));
  assert(!html.includes('A2 — Thermal context'));
  assert(html.includes('Show Global Mars terrain (MOLA)'));
  const available=renderToStaticMarkup(createElement(LayerPanel,{...props,availability:{geology:true,thermal:true}}));
  assert(available.includes('Show SIM 3464 geology'));
  assert(available.includes('Show THEMIS daytime visual context'));
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
