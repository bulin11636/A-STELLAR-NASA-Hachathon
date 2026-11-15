import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { act, createElement } from "react";
import { create, type ReactTestRenderer } from "react-test-renderer";
import { useRouteChat } from "../src/services/useRouteChat.ts";
import { buildAdvancedContext } from "../src/services/advancedContext.ts";
import { answer, attempt, deferred, failure, fixture, sessionMemory } from "./helpers/p0.ts";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = globalThis.fetch;
const descriptor = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
const routeId = fixture.result.route_id;
let renderer: ReactTestRenderer | null = null;
let memory: ReturnType<typeof sessionMemory>;
beforeEach(() => { memory = sessionMemory(); Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: memory }); });
afterEach(async () => {
  if (renderer) await act(() => renderer!.unmount()); renderer = null; globalThis.fetch = originalFetch;
  if (descriptor) Object.defineProperty(globalThis, "sessionStorage", descriptor); else delete (globalThis as any).sessionStorage;
});
async function harness(props: any = {}) {
  let current!: ReturnType<typeof useRouteChat>; let revisions = 0;
  const settings = { onRevision() { revisions++; }, ...props };
  function Harness(p: any) { current = useRouteChat(routeId, settings.onRevision, p.context, 0, false, p.selectionVersion ?? 0); return null; }
  await act(() => { renderer = create(createElement(Harness, settings)); });
  return { current: () => current, revisions: () => revisions, update: async (next: any) => { await act(() => renderer!.update(createElement(Harness, { ...settings, ...next }))); } };
}

test("chat eligible retry keeps its ID/message/context and sends the attempt version", async () => {
  const posts: any[] = []; let id = '';
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/attempts/')) return Response.json(attempt(id));
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); id = body.request_id; posts.push({ body, headers: init.headers });
      return posts.length === 1 ? failure() : Response.json(answer(routeId, body));
    }
    return Response.json({ messages: [] });
  };
  const context = buildAdvancedContext('shortest', [], ['terrain'], true);
  const h = await harness({ context }); await act(() => h.current().setText('Explain.'));
  await act(async () => h.current().submit()); assert(h.current().attempt?.retry_allowed); assert(!h.current().canSend);
  await act(async () => h.current().retry());
  assert.deepEqual(posts[1].body, posts[0].body); assert.equal(posts[1].headers['X-A-Stellar-Retry-Attempt'], '1');
  assert.equal(h.current().messages.length, 1); assert.equal(h.current().hasPending, false); assert.equal(memory.values.size, 0);
});

test("cooldown and unknown outcomes cannot execute a retry or duplicate send", async () => {
  for (const state of ['failed', 'unknown']) {
    let posts = 0; let id = '';
    globalThis.fetch = async (url, init) => {
      if (String(url).includes('/attempts/')) return Response.json(attempt(id, state, false, 2, state === 'failed' ? 30 : 0));
      if (init?.method === 'POST') { posts++; id = JSON.parse(String(init.body)).request_id; return failure(); }
      return Response.json({ messages: [] });
    };
    const h = await harness(); await act(() => h.current().setText('Explain.')); await act(async () => h.current().submit());
    await act(async () => { await h.current().retry(); await h.current().submit(); }); assert.equal(posts, 1);
    await act(() => renderer!.unmount()); renderer = null; memory.values.clear();
  }
});

test("changed Advanced context is a new explicit chat action with a new ID", async () => {
  const posts: any[] = []; let id = '';
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/attempts/')) return Response.json(attempt(id));
    if (init?.method === 'POST') { const body = JSON.parse(String(init.body)); posts.push(body); id = body.request_id; return failure(); }
    return Response.json({ messages: [] });
  };
  const context = buildAdvancedContext('shortest', [], ['terrain'], true);
  const h = await harness({ context }); await act(() => h.current().setText('Explain.')); await act(async () => h.current().submit());
  await h.update({ context: { ...context, analysis_focus: ['operations'] } });
  assert(h.current().canSend); await act(async () => h.current().submit());
  assert.equal(posts.length, 2); assert.notEqual(posts[0].request_id, posts[1].request_id);
  assert.deepEqual(posts[1].advanced_context.analysis_focus, ['operations']);
});

test("late chat revision cannot replace a newer selection", async () => {
  const pending = deferred<Response>(); let body: any;
  globalThis.fetch = async (_url, init) => {
    if (init?.method === 'POST') { body = JSON.parse(String(init.body)); return pending.promise; }
    return Response.json({ messages: [] });
  };
  const h = await harness(); await act(() => h.current().setText('Revise.')); let post!: Promise<void>;
  await act(() => { post = h.current().submit(); }); await h.update({ selectionVersion: 1 });
  await act(async () => { pending.resolve(Response.json({ ...answer(routeId, body), result: fixture.result, metadata: { ...fixture.metadata, parent_route_id: routeId } })); await post; });
  assert.equal(h.revisions(), 0); assert.equal(h.current().attempt?.state, 'unknown');
});

test("chat pending state survives remount without a generation call", async () => {
  let posts = 0; let id = '';
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/attempts/')) return Response.json(attempt(id, 'unknown', false));
    if (init?.method === 'POST') { posts++; id = JSON.parse(String(init.body)).request_id; throw new TypeError('offline'); }
    return Response.json({ messages: [] });
  };
  let h = await harness(); await act(() => h.current().setText('Explain.')); await act(async () => h.current().submit());
  await act(() => renderer!.unmount()); renderer = null;
  h = await harness(); assert.equal(h.current().attempt?.request_id, id); assert.equal(h.current().attempt?.state, 'unknown'); assert.equal(posts, 1);
  assert.equal(h.current().canSend, false);
});

test("an explanation-only chat refuses a contrary revision response", async () => {
  let id = '';
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/attempts/')) return Response.json(attempt(id, 'succeeded', false));
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); id = body.request_id;
      return Response.json({ ...answer(routeId, body), result: fixture.result, metadata: { ...fixture.metadata, parent_route_id: routeId } });
    }
    return Response.json({ messages: [] });
  };
  const h = await harness({ context: buildAdvancedContext('shortest', [], ['terrain'], false) });
  await act(() => h.current().setText('Explain.')); await act(async () => h.current().submit());
  assert.equal(h.revisions(), 0); assert.match(h.current().error!, /explanation-only/);
});
