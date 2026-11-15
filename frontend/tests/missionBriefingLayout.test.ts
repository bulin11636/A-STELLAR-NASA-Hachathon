import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("mission briefing separates conditions, attention, limitations, and technical details", () => {
  const component = readFileSync(new URL("../src/components/MissionBriefing.tsx", import.meta.url), "utf8");
  for (const heading of ["Known conditions", "Attention areas", "Limitations", "Technical details"]) assert.match(component, new RegExp(heading));
  assert.match(component, /metadata\.validation\.map_alignment/);
  assert.match(component, /assessment\.hard_gate_status !== "pass"/);
});
