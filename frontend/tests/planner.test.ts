import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, test } from "node:test";
import { act, createElement } from "react";
import { create, type ReactTestRenderer } from "react-test-renderer";
import { renderToStaticMarkup } from "react-dom/server";
import { useRoutePlanner } from "../src/services/useRoutePlanner.ts";
import RoutePlannerPanel from "../src/components/RoutePlannerPanel.tsx";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const fixture = JSON.parse(readFileSync(new URL("./fixtures/computed-route.json", import.meta.url), "utf8"));
const originalFetch = globalThis.fetch;
let renderer: ReactTestRenderer | null = null;
afterEach(async () => {
  if (renderer) await act(() => { renderer!.unmount(); });
  renderer = null; globalThis.fetch = originalFetch;
});

async function harness() {
  let current!: ReturnType<typeof useRoutePlanner>;
  function Harness() { current = useRoutePlanner(); return null; }
  await act(() => { renderer = create(createElement(Harness)); });
  await act(() => { current.changeMode("shortest"); current.setPickMode("start"); });
  await act(() => { current.selectPoint(fixture.metadata.request.start); });
  await act(() => { current.selectPoint(fixture.metadata.request.goal); });
  return () => current;
}

function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((done) => { resolve = done; });
  return { promise, resolve };
}

test("computed POST retrieves metadata and renders research labels, source, resolution and unknown metrics", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return Response.json(String(url).endsWith("/plan") ? fixture.result : fixture);
  };
  const current = await harness();
  await act(async () => { await current().submit(); });
  assert.deepEqual(calls, ["/api/v1/routes/plan", `/api/v1/routes/${fixture.result.route_id}`]);
  assert.equal(current().metadata?.route_id, fixture.result.route_id);
  assert.equal(current().metadataError, null);
  const html = renderToStaticMarkup(createElement(RoutePlannerPanel, { planner: current(), mapReady: true, onViewJezero() {} }));
  for (const value of ["COMPUTED / RESEARCH TERRAIN ONLY", "synthetic-plane", "20 × 30", "Terrain &amp; Traversability", "Not estimated", "Not assessed", "Computed geometry is displayed on NASA imagery"]) assert(html.includes(value), value);
  assert(!html.includes("MOCK / NOT SAFETY-VALIDATED"));
});

test("single-flight mock submission keeps null metrics and does not request computed metadata", async () => {
  const pending = deferred(); let calls = 0;
  globalThis.fetch = async () => { calls++; return pending.promise; };
  const current = await harness(); let first!: Promise<void>;
  await act(() => { first = current().submit(); void current().submit(); });
  assert.equal(calls, 1);
  const mock = { ...fixture.result, source: "mock", metrics: { distance_m: null, estimated_time_min: null, risk_score: null } };
  await act(async () => { pending.resolve(Response.json(mock)); await first; });
  assert.equal(current().result?.source, "mock");
  assert.equal(current().metadata, null); assert.equal(calls, 1);
});

test("mode and selection changes cancel metadata GET and discard a late response", async () => {
  for (const change of ["mode", "selection", "clear"] as const) {
    const pending = deferred(); let signal: AbortSignal | undefined;
    globalThis.fetch = async (url, init) => {
      if (String(url).endsWith("/plan")) return Response.json(fixture.result);
      signal = init?.signal ?? undefined; return pending.promise;
    };
    const current = await harness(); let submission!: Promise<void>;
    await act(async () => { submission = current().submit(); });
    assert(signal); assert.equal(current().result?.source, "computed");
    await act(() => {
      if (change === "mode") current().changeMode("safest");
      else if (change === "clear") current().clear();
      else current().setPickMode("start");
    });
    if (change === "selection") await act(() => { current().selectPoint(fixture.metadata.request.goal); });
    assert(signal.aborted);
    await act(async () => { pending.resolve(Response.json(fixture)); await submission; });
    assert.equal(current().result, null); assert.equal(current().metadata, null);
    assert.equal(current().status, "idle");
    await act(() => { renderer!.unmount(); }); renderer = null;
  }
});

test("late POST after clear or unmount never triggers a metadata GET", async () => {
  for (const unmount of [false, true]) {
    const pending = deferred(); let calls = 0; let signal: AbortSignal | undefined;
    globalThis.fetch = async (_url, init) => { calls++; signal = init?.signal ?? undefined; return pending.promise; };
    const current = await harness(); let submission!: Promise<void>;
    await act(() => { submission = current().submit(); });
    await act(() => { if (unmount) { renderer!.unmount(); renderer = null; } else current().clear(); });
    assert(signal?.aborted);
    await act(async () => { pending.resolve(Response.json(fixture.result)); await submission; });
    assert.equal(calls, 1); assert.equal(current().metadata, null);
    if (renderer) { await act(() => { renderer!.unmount(); }); renderer = null; }
  }
});

test("metadata mismatch or unavailable record is explicit while computed result remains inspectable", async () => {
  for (const mismatch of [false, true]) {
    globalThis.fetch = async (url) => {
      if (String(url).endsWith("/plan")) return Response.json(fixture.result);
      if (!mismatch) return Response.json({ error: { code: "ROUTE_NOT_FOUND", message: "Record unavailable.", details: null } }, { status: 404 });
      const altered = structuredClone(fixture); altered.result.metrics.distance_m += 1;
      return Response.json(altered);
    };
    const current = await harness();
    await act(async () => { await current().submit(); });
    assert.equal(current().status, "error"); assert(current().result);
    assert.equal(current().metadata, null);
    assert.match(current().metadataError!, mismatch ? /differs/ : /unavailable/);
    await act(() => { renderer!.unmount(); }); renderer = null;
  }
});

test("load backend example endpoints without a ready basemap and discard previous work", async () => {
  const current = await harness();
  await act(() => { current().clear(); current().selectionError("Outside the planning footprint."); });
  await act(() => { current().loadExample(fixture.metadata.request); });
  assert.deepEqual(current().start, fixture.metadata.request.start);
  assert.deepEqual(current().goal, fixture.metadata.request.goal);
  assert.equal(current().error, null);
  assert.equal(current().pickMode, "inspect");
  const html = renderToStaticMarkup(createElement(RoutePlannerPanel, {
    planner: current(), mapReady: false, onViewJezero() {},
    planningRegion: { id: "jezero", coordinate_system: fixture.result.coordinate_system,
      routing_available: true, routing_mode: "computed", planning: {
        roi_id: fixture.metadata.scope.roi_id, bounds: fixture.metadata.scope.bounds,
        resolution_m: [20, 30], example_request: fixture.metadata.request,
      } },
  }));
  assert(html.includes("Load in-coverage example endpoints"));
  assert(html.includes("Map coverage is larger than the planning window"));
  assert.match(html, /<button type="button">Plan Route<\/button>/);
});
