import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("route workspace exposes backend-owned leg timing and planning limits", () => {
  const map = readFileSync(new URL("../src/components/MarsMap.tsx", import.meta.url), "utf8");
  assert.match(map, /planner\.metadata\.legs\.map/);
  assert.match(map, /Actual cell size/);
  assert.match(map, /max_expanded_nodes/);
  assert.match(map, /Per-leg timing is unavailable/);
});
