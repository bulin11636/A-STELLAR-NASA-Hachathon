# Merged P0 integration gaps

Historical baseline review. The user subsequently authorized fixes; all six
findings are addressed in the [UI acceptance and walkthrough](P0_UI_ACCEPTANCE.md).
The audit script now verifies the repaired behavior.

Date: 2026-11-15 (UTC+08:00). Reviewed main: `87238e3` (merge of the completed
Sheng branch and Sam backend). `sam/backend` was fast-forwarded to that baseline.
This review changes no production frontend/backend source.

The merged branch contains working pieces, but it does not pass the complete P0
user-flow contract. The items below are observed integration gaps, not a request
to relax backend idempotency or validation. Frontend implementation remains with
Sheng; the backend recovery/policy contract remains authoritative.

## Observed verification

| Check | Result |
| --- | --- |
| Backend suite | 358 passed. |
| Frontend suite | 53 passed. |
| Production build | Passed. |
| Existing browser workflow | Passed: plan, eight-stop chat revisions, reload, preview controls and crater-scale display. |
| Focused P0 browser audit | Blocked: six reproducible gaps below. |
| Live model generation | None. All model responses were mocked. |

The existing browser workflow reloads before planning its second endpoint set.
That resets the React ref and therefore misses the completed-key reuse bug.
Passing this regression and the current unit suites does not establish that the
new Advanced or manual-recovery flows are complete.

## Browser-reproduced gaps

### P0-UI-01: a different plan reuses the completed idempotency key

Priority: blocks repeated planning in one page session.

Reproduce:

1. Load in-coverage example endpoints and select Plan Route; observe HTTP 200.
2. Without reloading, load crater-scale example endpoints and select Plan Route.
3. Observe HTTP 409 / PLAN_REQUEST_CONFLICT. Both POSTs used the same key with
   different bodies.

Source: [useRoutePlanner.ts](../frontend/src/services/useRoutePlanner.ts),
`planRequestId` at line 37, invalidation at lines 46–56 and key selection at
lines 104–109. The ref is initialized once and is not reset for a new action.

Acceptance: retain a key and the frozen original body while its outcome is
unresolved or a replay/retry is intended. A new intended plan with different
inputs must receive a new key. Test two successful different plans without a
page reload; do not weaken the backend's body/key binding.

### P0-UI-02: Advanced requirements do not execute plan then chat

Priority: blocks the central Advanced workflow.

Reproduce:

1. Select Advanced and load valid example endpoints.
2. Enter Additional requirements, then select the available Plan Route action.
3. The base plan succeeds; there is no chat POST, and the requirement is not
   transmitted. There is no Plan and Ask A0 button.
4. With all analysis focus options unchecked, the planning action also remains
   enabled.

Source: [RoutePlannerPanel.tsx](../frontend/src/components/RoutePlannerPanel.tsx),
lines 75–83, and [useRoutePlanner.ts](../frontend/src/services/useRoutePlanner.ts),
lines 93–137. `additionalRequirements` is stored but is never submitted.

Acceptance: provide the agreed Plan and Ask A0 flow. Validate focus and trimmed
requirements; send chat only after a successful persisted computed base route
and matching metadata. Use that persisted route's objective and ordered stops
for advanced_context. Preserve the base route on chat failure. Disclose the
additional A0 request and never retry it automatically.

### P0-UI-03: eligible planning failures have no manual retry action

Priority: blocks planned recovery.

Reproduce: return a fixture-backed failed plan and a status response with
`retry_allowed: true`, `attempt: 1`, and `retry_after_seconds: 0`. The UI displays
that manual retry is available but renders no retry button. No automatic retry
was observed.

Source: [RoutePlannerPanel.tsx](../frontend/src/components/RoutePlannerPanel.tsx),
line 88, and [useRoutePlanner.ts](../frontend/src/services/useRoutePlanner.ts),
lines 104–109. The transport supports a retry version, but the hook/action does
not pass one.

Acceptance: a deliberate eligible retry must retain the original key/body and
send X-A-Stellar-Retry-Attempt with the current attempt number. Honor cooldowns;
do not offer execution for unknown or non-retryable outcomes.

### P0-UI-04: chat failures have no durable status/retry flow

Priority: blocks planned chat recovery.

Reproduce: plan a real computed base route, then return a fixture-backed
retryable chat failure. The prior route remains visible, which is correct, but
there is no chat-attempt status GET, durable state display or retry button.

Source: [RouteChat.tsx](../frontend/src/components/RouteChat.tsx), lines 30–54,
and [chat.ts](../frontend/src/services/chat.ts). Chat preserves an ID for the same
text, but does not connect the existing chat status client or retry header.

Acceptance: expose the recorded attempt state, retain the complete original
body/ID/context, and permit only an explicit backend-eligible versioned retry.
An unknown outcome must never be automatically resubmitted. Changing Advanced
context must not reuse an ID bound to the old context.

### P0-UI-05: editing the next request removes the last successful route

Priority: violates result-preservation acceptance.

Reproduce: plan the in-coverage example successfully, then change its objective
from Shortest to Safest. The route preview and metadata disappear immediately,
before any replacement succeeds. A later failure therefore cannot retain that
last successful result.

Source: [useRoutePlanner.ts](../frontend/src/services/useRoutePlanner.ts),
lines 46–56 and 67. The same invalidate function clears input work and successful
result state. Existing older tests currently expect this clearing behavior.

Acceptance: distinguish draft inputs/in-flight work from the last successful
result. Keep the result and its metadata visible during edits and failed plan/
chat operations; replace them together after a valid success. Explicit Clear
may clear them. Update tests to the P0 requirement.

### P0-UI-06: Quick mode still exposes Advanced waypoint controls

Priority: product-mode contract mismatch.

Reproduce: open a fresh page in Quick mode. The required waypoint section,
ordered-coordinate editor and waypoint interaction are still present.

Source: [RoutePlannerPanel.tsx](../frontend/src/components/RoutePlannerPanel.tsx),
lines 48–68. Only analysis focus/requirements are gated by interfaceMode.

Acceptance: Quick exposes Start, Goal and objective for planning. Put required
waypoint creation/reordering/removal in Advanced, retain the 16-stop bound and
exact order, and ensure hidden Advanced stops do not silently affect Quick.

## Additional code-review checks for the frontend owner

These are separate from the six browser-reproduced findings:

- [A0Status.tsx](../frontend/src/components/A0Status.tsx), lines 19–32, displays
  mode/configuration and returned usage, but does not surface the backend's
  planning/storage checks or passive provider observation. Finish the agreed
  runtime distinctions without claiming current provider access.
- [RouteChat.tsx](../frontend/src/components/RouteChat.tsx), lines 13 and 37–40,
  chooses a pending ID from route and message only. Include the frozen Advanced
  context in action identity; do not send changed context under an old ID.
- Required-stop client validation still needs the agreed consecutive-duplicate
  check. Backend validation already rejects those inputs before generation.
- Extend P0 integration tests to cover a request's running/unknown outcomes,
  restart recovery and stale responses. A browser test that covers only happy
  paths and reloads before every new plan cannot verify those conditions.

## Reproduce the focused audit

Install the existing frontend dependencies, build it and make Chromium available
through the project's Playwright installation. From the repository root:

```bash
node scripts/audit_p0_ui.mjs \
  --dataset-dir /absolute/path/to/dataset \
  --python /path/to/python
```

The script starts the real local API and CTX planner with a mocked provider on
an isolated port/state directory. Recovery cases use the shared backend fixtures
at the browser transport boundary. External NASA requests are blocked. It writes
screenshots and summary.json under ignored `data/processed/p0-ui-audit/`.
Exit 1 with status `blocked` means observed product gaps; status `failed` means
the audit itself could not complete. No live provider requests are made.

Observed local evidence:

- Focused audit: `p0-ui-audit/run-2026-11-15T03-55-22-158Z/summary.json`.
- Screenshots: `new-plan.png`, `advanced.png`, `plan-retry.png`, `chat-retry.png`
  and `previous-route.png` in that directory.
- Existing browser regression: `ui-verification/run-2026-11-15T03-51-34-765Z/summary.json`.

NASA registration remains unverified. This review does not certify map alignment,
route safety, scientific constraint fusion or a complete P0 product delivery.
