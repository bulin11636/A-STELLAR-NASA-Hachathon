import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { GLOBAL_LAYER_ID, JEZERO_LAYER_ID, LAYER_ID } from "../src/map/marsWmts.ts";

test("the global map and Jezero imagery demo-overlay copy stay explicit", () => {
  assert.equal(LAYER_ID, GLOBAL_LAYER_ID);
  assert.equal(JEZERO_LAYER_ID, "NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018");
  const map = readFileSync(new URL("../src/components/MarsMap.tsx", import.meta.url), "utf8");
  assert.match(map, /loadMarsWmts\(controller\.signal, JEZERO_LAYER_ID\)/);
  assert.match(map, /Enabled for the demo using the documented M20 DEM-to-WMTS coordinate conversion/);
  assert.match(map, /NASA imagery demo overlay/);
});
