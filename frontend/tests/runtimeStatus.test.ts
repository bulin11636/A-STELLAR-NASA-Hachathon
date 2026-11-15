import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { act, createElement } from "react";
import { create, type ReactTestRenderer } from "react-test-renderer";
import A0Status from "../src/components/A0Status.tsx";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = globalThis.fetch;
let renderer: ReactTestRenderer | null = null;
afterEach(async () => { if (renderer) await act(() => renderer!.unmount()); renderer = null; globalThis.fetch = originalFetch; });
const status = { mode: 'agentic', model: 'gpt-6.1-sol', reasoning_effort: 'medium', configured: true,
  checks: { planning: true, storage: false, model_credentials: true }, budget: null,
  provider: { availability: 'not_checked', last_request_outcome: 'rejected', last_http_status: 429 } };

test("runtime separates source/storage/configuration and historic provider outcome", async () => {
  globalThis.fetch = async () => Response.json(status);
  await act(() => { renderer = create(createElement(A0Status, { routingMode: 'computed' })); });
  const text = JSON.stringify(renderer!.toJSON());
  for (const expected of ['computed / agentic', 'Dataset/profile:', 'unavailable', 'configured', 'not checked', '429']) assert(text.includes(expected), expected);
  assert(!text.includes('Confirmed provider access'));
});

test("malformed provider state is a typed error rather than a render failure", async () => {
  globalThis.fetch = async () => Response.json({ ...status, provider: { availability: {}, last_request_outcome: [], last_http_status: null } });
  await act(() => { renderer = create(createElement(A0Status, {})); });
  assert.match(JSON.stringify(renderer!.toJSON()), /Invalid provider observation/);
});
