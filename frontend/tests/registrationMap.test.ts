import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { LAYER_ID } from "../src/map/marsWmts.ts";

test("the NASA Jezero imagery and registration-pending copy stay explicit", () => {
  assert.equal(LAYER_ID, "NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018");
  const map = readFileSync(new URL("../src/components/MarsMap.tsx", import.meta.url), "utf8");
  assert.match(map, /Pending independent NASA WMTS, wire-coordinate, and DEM feature controls/);
  assert.match(map, /Computed geometry remains hidden/);
});
