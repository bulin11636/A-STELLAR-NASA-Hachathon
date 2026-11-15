import assert from "node:assert/strict";
import { test } from "node:test";
import { buildAdvancedContext } from "../src/services/advancedContext.ts";

test("advanced context preserves objective, waypoint order, focus, and revision permission", () => {
  const stops = [{ longitude: 77.4, latitude: 18.4 }, { longitude: 77.5, latitude: 18.5 }];
  assert.deepEqual(buildAdvancedContext("safest", stops, ["terrain", "science"], true), {
    schema_version: "1", interface_mode: "advanced", route_objective: "safest",
    required_waypoints: stops, analysis_focus: ["terrain", "science"], allow_supported_revision: true,
  });
  assert.throws(() => buildAdvancedContext("shortest", [], [], false));
  assert.throws(() => buildAdvancedContext("shortest", [], ["terrain", "terrain"], false));
});
