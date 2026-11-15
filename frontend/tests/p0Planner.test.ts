import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { act, createElement } from "react";
import { create, type ReactTestRenderer } from "react-test-renderer";
import { renderToStaticMarkup } from "react-dom/server";
import { useRoutePlanner } from "../src/services/useRoutePlanner.ts";
import RoutePlannerPanel from "../src/components/RoutePlannerPanel.tsx";
import { answer, attempt, deferred, failure, fixture, sessionMemory, storedFor } from "./helpers/p0.ts";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = globalThis.fetch;
const descriptor = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
let renderer: ReactTestRenderer | null = null;
let memory: ReturnType<typeof sessionMemory>;
beforeEach(() => { memory = sessionMemory(); Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: memory }); });
afterEach(async () => {
  if (renderer) await act(() => renderer!.unmount()); renderer = null; globalThis.fetch = originalFetch;
  if (descriptor) Object.defineProperty(globalThis, "sessionStorage", descriptor); else delete (globalThis as any).sessionStorage;
});
async function harness(load = true) {
  let current!: ReturnType<typeof useRoutePlanner>;
  function Harness() { current = useRoutePlanner(); return null; }
  await act(() => { renderer = create(createElement(Harness)); });
  if (load) await act(() => current.loadExample(fixture.metadata.request));
  return () => current;
}
function mockSuccess(calls: any[] = []) {
  let stored = fixture;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null, headers: init?.headers });
    if (String(url).endsWith('/plan')) { stored = storedFor(JSON.parse(String(init?.body))); return Response.json(stored.result); }
    if (String(url).endsWith('/chat')) return Response.json(answer(stored.result.route_id, JSON.parse(String(init?.body))));
    return Response.json(stored);
  };
  return calls;
}

test("different planning actions receive new keys without reload", async () => {
  const calls = mockSuccess(); const current = await harness();
  await act(async () => current().submit(true));
  const first = current().result;
  await act(() => current().changeMode("safest"));
  assert.equal(current().result, first, "Editing must preserve the successful result");
  await act(async () => current().submit(true));
  const posts = calls.filter(c => c.method === 'POST');
  assert.equal(posts.length, 2); assert.notEqual(posts[0].headers['Idempotency-Key'], posts[1].headers['Idempotency-Key']);
  assert.equal(current().metadata?.request.mode, 'safest'); assert.equal(memory.values.size, 0);
});

test("failed replacement preserves previous result and versioned retry uses frozen body/key", async () => {
  let stored = fixture; const posts: any[] = []; let lastId = '';
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/requests/')) return Response.json(attempt(lastId));
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); const headers = init.headers as Record<string,string>; lastId = headers['Idempotency-Key']; posts.push({ body, headers });
      if (posts.length === 2) return failure();
      stored = storedFor(body, posts.length === 1 ? '1' : '3'); return Response.json(stored.result);
    }
    return Response.json(stored);
  };
  const current = await harness(); await act(async () => current().submit(true)); const previous = current().result;
  await act(() => current().changeMode('safest')); await act(async () => current().submit(true));
  assert.equal(current().result, previous); assert(current().attemptStatus?.retry_allowed); assert.equal(posts.length, 2);
  await act(() => current().changeMode('shortest'));
  await act(async () => current().retry());
  assert.deepEqual(posts[2].body, posts[1].body); assert.equal(posts[2].headers['Idempotency-Key'], posts[1].headers['Idempotency-Key']);
  assert.equal(posts[2].headers['X-A-Stellar-Retry-Attempt'], '1'); assert.equal(current().result?.mode, 'safest');
});

test("unknown outcome never executes again automatically or through retry", async () => {
  let posts = 0; let id = '';
  globalThis.fetch = async (url, init) => {
    if (init?.method === 'POST') { posts++; id = (init.headers as any)['Idempotency-Key']; throw new TypeError('offline'); }
    return Response.json(attempt(id, 'unknown', false));
  };
  const current = await harness(); await act(async () => current().submit(true));
  assert.equal(current().attemptStatus?.state, 'unknown'); assert.equal(current().canSubmit, false);
  await act(async () => { await current().submit(true); await current().retry(); await current().refreshAttempt(); });
  assert.equal(posts, 1);
});

test("pending plan survives remount and only explicit recovery replays the saved key", async () => {
  let posts = 0; let id = ''; let savedBody: any; let complete = false;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/requests/')) return Response.json(attempt(id, complete ? 'succeeded' : 'unknown', false));
    if (init?.method === 'POST') {
      posts++; const nextId = (init.headers as any)['Idempotency-Key']; if (id) assert.equal(nextId, id); else id = nextId;
      savedBody = JSON.parse(String(init.body)); if (!complete) throw new TypeError('offline');
      assert.equal((init.headers as any)['X-A-Stellar-Retry-Attempt'], '1');
      return Response.json(storedFor(savedBody).result);
    }
    return Response.json(storedFor(savedBody));
  };
  let current = await harness(); await act(async () => current().submit(true));
  await act(() => renderer!.unmount()); renderer = null;
  current = await harness(false);
  assert.equal(current().attemptStatus?.request_id, id); assert.equal(posts, 1);
  complete = true; await act(async () => current().refreshAttempt()); assert.equal(posts, 1);
  await act(async () => current().recover()); assert.equal(posts, 2); assert(current().metadata); assert.equal(memory.values.size, 0);
});

test("Advanced waits for matching persisted metadata before one bounded chat request", async () => {
  const calls = mockSuccess(); const current = await harness();
  await act(() => current().setInterfaceMode('advanced')); assert(!current().canSubmit);
  await act(() => { current().setAdditionalRequirements('  Explain terrain limitations.  '); current().setAllowSupportedRevision(false); });
  assert(current().canSubmit); await act(async () => current().submit(true));
  assert.deepEqual(calls.map(c => c.url), ['/api/v1/routes/plan', `/api/v1/routes/${fixture.result.route_id}`, `/api/v1/routes/${fixture.result.route_id}/chat`]);
  const chat = calls[2].body;
  assert.equal(chat.message, 'Explain terrain limitations.');
  assert.deepEqual(chat.advanced_context, { schema_version: '1', interface_mode: 'advanced', route_objective: 'shortest', required_waypoints: [], analysis_focus: ['terrain'], allow_supported_revision: false });
  assert.equal(current().result?.route_id, fixture.result.route_id); assert.equal(current().advancedReply?.result, null);
});

test("Advanced never sends chat after failed base plan or unavailable metadata", async () => {
  for (const failPlan of [true, false]) {
    let chatPosts = 0; let key = '';
    globalThis.fetch = async (url, init) => {
      if (String(url).endsWith('/chat')) { chatPosts++; throw new Error('Must not chat'); }
      if (String(url).includes('/requests/')) return Response.json(attempt(key, failPlan ? 'failed' : 'succeeded', false));
      if (init?.method === 'POST') { key = (init.headers as any)['Idempotency-Key']; return failPlan ? failure() : Response.json(fixture.result); }
      return Response.json({ error: { code: 'ROUTE_NOT_FOUND', message: 'Unavailable.', details: null } }, { status: 404 });
    };
    const current = await harness(); await act(() => { current().setInterfaceMode('advanced'); current().setAdditionalRequirements('Explain.'); });
    await act(async () => current().submit(true)); assert.equal(chatPosts, 0); assert.equal(current().status, 'error');
    await act(() => renderer!.unmount()); renderer = null; memory.values.clear();
  }
});

test("Advanced chat failure preserves base route and retry sends the original context/version", async () => {
  let key = ''; const chatBodies: any[] = []; let chatCalls = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/attempts/')) return Response.json(attempt(key));
    if (String(url).endsWith('/plan')) return Response.json(fixture.result);
    if (String(url).endsWith('/chat')) {
      const body = JSON.parse(String(init?.body)); key = body.request_id; chatBodies.push({ body, headers: init?.headers }); chatCalls++;
      return chatCalls === 1 ? failure() : Response.json(answer(fixture.result.route_id, body));
    }
    return Response.json(fixture);
  };
  const current = await harness(); await act(() => { current().setInterfaceMode('advanced'); current().setAdditionalRequirements('Explain.'); });
  await act(async () => current().submit(true)); assert.equal(current().result?.route_id, fixture.result.route_id); assert.equal(current().pendingKind, 'chat');
  await act(() => current().setAnalysisFocus(['operations'])); await act(async () => current().retry());
  assert.deepEqual(chatBodies[1].body, chatBodies[0].body); assert.equal(chatBodies[1].headers['X-A-Stellar-Retry-Attempt'], '1');
  assert.equal(chatCalls, 2); assert.equal(current().status, 'success');
});

test("Quick ignores hidden Advanced waypoints and requirements", async () => {
  const calls = mockSuccess(); const current = await harness();
  await act(() => current().setInterfaceMode('advanced'));
  const point = fixture.result.route[3]; await act(() => current().addWaypoint(point));
  await act(() => { current().setAdditionalRequirements('Explain.'); current().setInterfaceMode('quick'); });
  assert.equal(current().waypoints.length, 1); await act(async () => current().submit(true));
  assert.equal(calls.filter(c => c.method === 'POST').length, 1); assert.equal(calls[0].body.waypoints, undefined);
  const html = renderToStaticMarkup(createElement(RoutePlannerPanel, { planner: current(), mapReady: false, onViewJezero() {} }));
  assert(!html.includes('aria-label="Required waypoints"')); assert(!html.includes('Pick Waypoint</button>'));
});

test("consecutive stop duplicates are rejected before any network request", async () => {
  const calls = mockSuccess(); const current = await harness(); await act(() => current().setInterfaceMode('advanced'));
  await act(() => current().addWaypoint(fixture.metadata.request.start));
  assert.equal(current().waypoints.length, 0); assert.match(current().error!.message, /Consecutive/); assert.equal(calls.length, 0);
});

test("late status read cannot overwrite a newer successful plan", async () => {
  const delayed = deferred<Response>(); let posts = 0; let stored = fixture;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/requests/')) return delayed.promise;
    if (init?.method === 'POST') { posts++; if (posts === 1) return failure(); stored = storedFor(JSON.parse(String(init.body))); return Response.json(stored.result); }
    return Response.json(stored);
  };
  const current = await harness(); let first!: Promise<void>;
  await act(() => { first = current().submit(true); });
  await act(() => current().changeMode('safest')); await act(async () => current().submit(true));
  await act(async () => { delayed.resolve(Response.json(attempt('old_request_00000001', 'unknown', false))); await first; });
  assert.equal(current().status, 'success'); assert.equal(current().result?.mode, 'safest'); assert.equal(current().attemptStatus?.state, 'succeeded');
});

test("walking mission is explicit, validated, frozen for retry and cleared", async () => {
  const calls = mockSuccess(); const current = await harness();
  await act(() => { current().setInterfaceMode('advanced'); current().setAdditionalRequirements('Explain mission assumptions.'); current().setWalkingSpeed('0'); });
  assert.equal(current().canSubmit,false); assert.match(current().inputError!,/positive walking speed/);
  await act(() => { current().setWalkingSpeed('1.2'); current().setWaypointDwell('4'); current().setRequiredAnalyses(['A2','A3']); });
  await act(async () => current().submit(true));
  const mission=calls.find(c=>c.url.endsWith('/plan')).body.mission;
  assert.deepEqual(mission,{mode:'walking',speed_m_s:1.2,stop_minutes_per_waypoint:4,exposure_duration_min:null,radiation_budget_usv:null,required_analyses:['A2','A3']});
  assert.equal(current().walkingSpeed,'1.2');
  await act(() => current().clear());
  assert.equal(current().walkingSpeed,'');assert.equal(current().waypointDwell,'0');assert.deepEqual(current().requiredAnalyses,[]);
});

test("Quick requests omit Advanced walking assumptions", async () => {
  const calls=mockSuccess();const current=await harness();
  await act(() => {current().setInterfaceMode('advanced');current().setWalkingSpeed('1');current().setRequiredAnalyses(['A3']);});
  await act(() => current().setInterfaceMode('quick'));
  await act(async () => current().submit(true));
  assert.equal(calls.find(c=>c.url.endsWith('/plan')).body.mission,undefined);
});

test("P1 profile and resolution are serialized and retained after metadata retrieval", async () => {
  const calls=mockSuccess();const current=await harness();
  await act(()=>{ current().changeMode('safest');current().setMissionProfile('balanced');current().setResolutionProfile('fine'); });
  await act(async()=>current().submit(true));
  const body=calls.find(c=>c.url.endsWith('/plan')).body;
  assert.equal(body.mission_profile,'balanced');assert.equal(body.resolution_profile,'fine');
  assert.equal(current().missionProfile,'balanced');assert.equal(current().resolutionProfile,'fine');
  await act(()=>current().loadExample(fixture.metadata.request));
  assert.equal(current().missionProfile,null);assert.equal(current().resolutionProfile,null);
});
