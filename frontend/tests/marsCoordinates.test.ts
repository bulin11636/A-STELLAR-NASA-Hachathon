import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { apiCoordinateToMapView, COORDINATE_ADAPTER_VALIDATED, MAP_REGISTRATION_VALIDATED, mapViewToApiCoordinate, routeToMapSegments, validateApiCoordinate } from "../src/geo/marsCoordinates.ts";

const use = "mock-integration-only";

test("Jezero shared fixture round-trips for mock integration, without asserting geospatial accuracy", () => {
  const fixture = JSON.parse(readFileSync(new URL("../../data/fixtures/jezero-coordinate.json", import.meta.url), "utf8"));
  assert.equal(COORDINATE_ADAPTER_VALIDATED, true);
  assert.equal(MAP_REGISTRATION_VALIDATED, false);
  assert.equal(fixture.coordinate_convention_validated, false);
  assert.deepEqual(mapViewToApiCoordinate(fixture.assumed_map_view, use), fixture.expected_api_coordinate);
  assert.deepEqual(apiCoordinateToMapView(fixture.expected_api_coordinate, use), fixture.assumed_map_view);
});

test("WMTS display transforms between planetocentric API and planetographic Mars 2000 latitude", () => {
  const wire = { longitude: 77.4509, latitude: 18.4446 };
  const view = apiCoordinateToMapView(wire, "wmts-display");
  assert.equal(view[0], wire.longitude);
  assert.notEqual(view[1], wire.latitude);
  assert(Math.abs(view[1] - 18.6486) < 0.001);
  const roundTrip = mapViewToApiCoordinate(view, "wmts-display");
  assert(Math.abs(roundTrip.longitude - wire.longitude) < 1e-12);
  assert(Math.abs(roundTrip.latitude - wire.latitude) < 1e-12);
  assert.deepEqual(apiCoordinateToMapView({ longitude: 180, latitude: 90 }, "wmts-display"), [-180, 90]);
});

test("longitude normalization and display seam are explicit", () => {
  for (const [native, wire] of [[-180, 180], [-0.5, 359.5], [0, 0], [77.4509, 77.4509], [180, 180]]) {
    assert.equal(mapViewToApiCoordinate([native, 18], use).longitude, wire);
  }
  assert.deepEqual(apiCoordinateToMapView({ longitude: 359.5, latitude: -90 }, use), [-0.5, -90]);
  assert.deepEqual(apiCoordinateToMapView({ longitude: 180, latitude: 90 }, use), [-180, 90]);
});

test("invalid coordinates are rejected instead of clamped or coerced", () => {
  for (const longitude of [-1, 360, NaN, Infinity, "77", null, undefined]) {
    assert.throws(() => validateApiCoordinate({ longitude, latitude: 18 }));
  }
  for (const latitude of [-91, 91, NaN, Infinity, "18", null, undefined]) {
    assert.throws(() => validateApiCoordinate({ longitude: 77, latitude }));
  }
  for (const point of [[181, 0], [-181, 0], [0, 91], [NaN, 0], [0], [0, 0, 0]]) {
    assert.throws(() => mapViewToApiCoordinate(point, use));
  }
  assert.throws(() => mapViewToApiCoordinate([77, 18], undefined as never));
  assert.throws(() => apiCoordinateToMapView({ longitude: 77, latitude: 18 }, undefined as never));
});

test("routes crossing the display seam are split without a false trans-Mars segment", () => {
  const segments = routeToMapSegments([{ longitude: 179, latitude: 10 }, { longitude: 181, latitude: 12 }], use);
  assert.deepEqual(segments, [[[179, 10], [180, 11]], [[-180, 11], [-179, 12]]]);
  const reverse = routeToMapSegments([{ longitude: 181, latitude: 12 }, { longitude: 179, latitude: 10 }], use);
  assert.deepEqual(reverse, [[[-179, 12], [-180, 11]], [[180, 11], [179, 10]]]);
});
