import test from "node:test";
import assert from "node:assert/strict";
import { fitRoute, zoomViewport } from "../src/geo/routeViewport.ts";

test("nearby stops fit their route rather than the crater footprint", () => {
  const view = fitRoute([[45_000,30_000],[45_020,30_010]],160);
  assert.equal(view.width,160);
  assert.equal(view.height,160);
  assert.equal(view.x+view.width/2,45_010);
  assert.equal(view.y+view.height/2,30_005);
});

test("regional fit preserves metric aspect and zoom bounds preserve the center", () => {
  const view = fitRoute([[0,0],[60_000,40_000]],160);
  assert.equal(view.width,78_000);
  assert.equal(view.width,view.height);
  const close = zoomViewport(view,.000001,5,200_000);
  assert.equal(close.width,5);
  assert.equal(close.x+close.width/2,30_000);
  const far = zoomViewport(view,100,5,200_000);
  assert.equal(far.width,200_000);
  assert.equal(far.y+far.height/2,20_000);
});
