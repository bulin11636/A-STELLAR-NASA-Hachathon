import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError } from "../src/services/apiClient.ts";
import { decodeRequestAttemptStatus, getChatAttemptStatus, getPlanRequestStatus } from "../src/services/attempts.ts";

const originalFetch = globalThis.fetch;
const requestId = "request_1234567890";
const routeId = "route-" + "a".repeat(32);

afterEach(() => { globalThis.fetch = originalFetch; });

function status(overrides: Record<string, unknown> = {}) {
  return { request_id: requestId, state: "failed", attempt: 2, retry_allowed: true,
    retry_after_seconds: 3, error: { code: "PROVIDER_REJECTED", message: "Try again later.", details: null },
    updated_at: "2026-11-14T08:00:00Z", ...overrides };
}

test("request attempt decoder accepts all documented states and rejects malformed status", () => {
  for (const state of ["running", "succeeded", "failed", "unknown"]) {
    assert.equal(decodeRequestAttemptStatus(status({ state })).state, state);
  }
  for (const invalid of [
    status({ request_id: "short" }), status({ state: "pending" }), status({ attempt: 0 }),
    status({ retry_after_seconds: -1 }), status({ retry_allowed: "yes" }),
    status({ error: { code: "", message: "x", details: null } }), status({ updated_at: 10 }),
  ]) assert.throws(() => decodeRequestAttemptStatus(invalid));
});

test("plan and chat status requests use the canonical endpoints and reject invalid identifiers locally", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (url, init) => {
    calls.push(String(url)); assert.equal(init?.method, "GET");
    return Response.json(status());
  };
  assert.equal((await getPlanRequestStatus(requestId)).attempt, 2);
  assert.equal((await getChatAttemptStatus(routeId, requestId)).retry_allowed, true);
  assert.deepEqual(calls, [`/api/v1/routes/requests/${requestId}`, `/api/v1/routes/${routeId}/chat/attempts/${requestId}`]);
  assert.throws(() => getPlanRequestStatus("invalid"), ApiError);
  assert.throws(() => getChatAttemptStatus("route-invalid", requestId), ApiError);
});
