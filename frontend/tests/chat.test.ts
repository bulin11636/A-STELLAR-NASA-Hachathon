import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, test } from "node:test";
import { act, createElement } from "react";
import { create, type ReactTestRenderer } from "react-test-renderer";
import { renderToStaticMarkup } from "react-dom/server";
import { decodeChat, sendChat } from "../src/services/chat.ts";
import RouteChat from "../src/components/RouteChat.tsx";
import RoutePreview from "../src/components/RoutePreview.tsx";
import { decodeRouteResponse } from "../src/services/routes.ts";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const stored = JSON.parse(readFileSync(new URL("./fixtures/computed-route.json", import.meta.url), "utf8"));
const parent = "route-" + "2".repeat(32);
const originalFetch = globalThis.fetch;
let renderer: ReactTestRenderer | null = null;
afterEach(async () => {
  if (renderer) await act(() => { renderer!.unmount(); });
  renderer = null; globalThis.fetch = originalFetch;
});
function message(replan = false) {
  return { message_id: "message-0000000001", route_id: parent, created_at: "2026-11-14T08:00:00Z",
    user_message: "Explain or revise", assistant_message: "Terrain-only answer.", usage: null,
    result: replan ? stored.result : null,
    metadata: replan ? { ...stored.metadata, parent_route_id: parent } : null };
}

test("chat decodes answers and parent-linked revisions; rejects mismatched or malformed records", () => {
  assert.equal(decodeChat(message(), parent).result, null);
  assert.equal(decodeChat(message(true), parent).result?.route_id, stored.result.route_id);
  const invalid = message(true); invalid.metadata!.parent_route_id = "route-" + "3".repeat(32);
  assert.throws(() => decodeChat(invalid, parent));
  assert.throws(() => decodeChat({ ...message(), usage: { calls: -1 } }, parent));
  assert.throws(() => decodeChat(message(), stored.result.route_id));
});

test("chat transport sends one bounded route-scoped request and preserves idempotency ID", async () => {
  let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls++;
    assert.equal(url, `/api/v1/routes/${parent}/chat`);
    assert.deepEqual(JSON.parse(init!.body as string), { message: "Why?", request_id: "request-0000000001" });
    return Response.json(message());
  };
  await sendChat(parent, "Why?", "request-0000000001");
  assert.equal(calls, 1);
});

test("route chat displays failed requests while preserving the current route", async () => {
  globalThis.fetch = async (_url, init) => init?.method === "POST"
    ? Response.json({ error: { code: "A0_BUDGET_EXHAUSTED", message: "Budget exhausted.", details: null } }, { status: 429 })
    : Response.json({ messages: [] });
  let revisions = 0;
  await act(() => { renderer = create(createElement(RouteChat, { routeId: parent, onRevision() { revisions++; } })); });
  await act(() => { renderer!.root.findByType("textarea").props.onChange({ target: { value: "Why?" } }); });
  await act(async () => { await renderer!.root.findByType("form").props.onSubmit({ preventDefault() {} }); });
  assert.equal(revisions, 0);
  assert.match(JSON.stringify(renderer!.toJSON()), /Budget exhausted/);
});

test("late chat revision after changing route is cancelled and never applied", async () => {
  let resolve!: (r: Response) => void;
  let sentSignal: AbortSignal | undefined;
  globalThis.fetch = async (_url, init) => {
    if (init?.method !== "POST") return Response.json({ messages: [] });
    sentSignal = init.signal ?? undefined;
    return new Promise<Response>((done) => { resolve = done; });
  };
  let revisions = 0;
  const props = { routeId: parent, onRevision() { revisions++; } };
  await act(() => { renderer = create(createElement(RouteChat, props)); });
  await act(() => { renderer!.root.findByType("textarea").props.onChange({ target: { value: "Use safest" } }); });
  let pending!: Promise<void>;
  await act(() => { pending = renderer!.root.findByType("form").props.onSubmit({ preventDefault() {} }); });
  await act(() => { renderer!.update(createElement(RouteChat, { ...props, routeId: stored.result.route_id })); });
  assert(sentSignal?.aborted);
  await act(async () => { resolve(Response.json(message(true))); await pending; });
  assert.equal(revisions, 0);
});

test("DEM preview shows computed geometry independently of NASA registration", () => {
  const html = renderToStaticMarkup(createElement(RoutePreview, { result: stored.result, metadata: stored.metadata }));
  assert(html.includes("<polyline"));
  assert(html.includes("NASA basemap registration remains unverified"));
});

test("route response must preserve required waypoint order", () => {
  const middle = stored.result.route[Math.floor(stored.result.route.length / 2)];
  assert.equal(decodeRouteResponse(stored.result, { ...stored.metadata.request, waypoints: [middle] }).source, "computed");
  assert.throws(() => decodeRouteResponse(stored.result, { ...stored.metadata.request,
    waypoints: [stored.result.route[stored.result.route.length - 1], stored.result.route[0]] }));
});
