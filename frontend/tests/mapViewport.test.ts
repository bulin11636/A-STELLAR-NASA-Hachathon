import assert from "node:assert/strict";
import test from "node:test";
import { missionViewport } from "../src/map/mapViewport.ts";
import { apiCoordinateToMapView } from "../src/geo/marsCoordinates.ts";

test("mission viewport keeps a human-scale minimum span around a single stop", () => {
  const point = { longitude: 77.4, latitude: 18.4 };
  const [x, y] = apiCoordinateToMapView(point, "wmts-display");
  const extent = missionViewport([point], 0.025);
  assert.deepEqual(extent, [x - 0.0125, y - 0.0125, x + 0.0125, y + 0.0125]);
});

test("mission viewport includes both stops instead of applying a fixed zoom", () => {
  const extent = missionViewport([{ longitude: 77.2, latitude: 18.3 }, { longitude: 77.6, latitude: 18.6 }], 0.025);
  assert(extent);
  const start = apiCoordinateToMapView({ longitude: 77.2, latitude: 18.3 }, "wmts-display");
  const goal = apiCoordinateToMapView({ longitude: 77.6, latitude: 18.6 }, "wmts-display");
  const epsilon = 1e-9;
  assert(extent[0] <= Math.min(start[0], goal[0]) + epsilon && extent[2] >= Math.max(start[0], goal[0]) - epsilon);
  assert(extent[1] <= Math.min(start[1], goal[1]) + epsilon && extent[3] >= Math.max(start[1], goal[1]) - epsilon);
});
