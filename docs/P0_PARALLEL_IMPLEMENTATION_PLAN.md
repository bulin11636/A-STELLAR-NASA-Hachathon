# P0 Parallel Implementation Plan

## Ownership

| Owner | Area | Branching intent |
| --- | --- | --- |
| **Sheng** | Frontend: React, TypeScript, OpenLayers UI, API client, state, tests | Work only under `frontend/` unless a shared contract document needs an agreed update. |
| **Sam** | Backend: FastAPI, request recovery, persistence, provider handling, API tests | Work under `backend/`, `scripts/`, and backend-facing documentation. |

Both owners may work in parallel. Do not wait for the other implementation to
finish: use the shared contract and fixtures below. Neither owner should rewrite
the other's source files.

## Shared P0 contract — freeze before implementation

The existing successful route and chat schemas remain unchanged. The backend is
the source of truth for request state.

```text
POST /api/v1/routes/plan
  Header: Idempotency-Key: <16–64 ASCII letters, digits, underscores, or hyphens>

GET /api/v1/routes/requests/{request_id}

POST /api/v1/routes/{route_id}/chat
  Body: { "message": "...", "request_id": "..." }

GET /api/v1/routes/{route_id}/chat/attempts/{request_id}
```

Status responses must provide this stable shape:

```json
{
  "request_id": "string",
  "state": "running | succeeded | failed | unknown",
  "attempt": 1,
  "retry_allowed": false,
  "retry_after_seconds": null,
  "error": null,
  "updated_at": "ISO-8601 timestamp or null"
}
```

Rules:

- `running`: the client waits or polls; it must not create another model request.
- `succeeded`: replaying the original request/key returns the original result.
- `failed`: show the recorded error. Retry only when `retry_allowed` is true.
- `unknown`: never retry automatically; the original outcome is uncertain.
- A retry must retain the original request body, request ID/key, and backend
  attempt version. Honor `retry_after_seconds`.
- Expected failures must use the existing JSON error envelope. Do not expose
  traceback text, HTML error pages, file paths, credentials, or provider secrets.

## Sheng — Frontend implementation work

### Scope and restrictions

- Own `frontend/` source and frontend tests.
- Keep all product UI text, controls, errors, and newly added code comments in English.
- Reuse the relative `/api/v1` transport, typed decoding, AbortController,
  single-flight behavior, and stale-response protection already in the project.
- Do not make browser-side model calls or store an OpenAI key in frontend code.
- Do not render computed route geometry on the NASA basemap until independent
  NASA WMTS/wire/DEM registration is verified.

### SHENG-FE-1 — Typed request-status client and fixtures

- [ ] Define a `RequestAttemptStatus` TypeScript type and strict decoder.
- [ ] Add `getPlanRequestStatus(requestId)`.
- [ ] Add `getChatAttemptStatus(routeId, requestId)`.
- [ ] Add frontend fixtures for `running`, `succeeded`, retryable `failed`,
  non-retryable `failed`, and `unknown`.
- [ ] Add decoder tests for valid and malformed payloads.

### SHENG-FE-2 — Computed plan lifecycle

- [ ] Generate one `Idempotency-Key` per intended computed planning action.
- [ ] Retain that key until the outcome is known; do not create a replacement key
  after a timeout or page re-render.
- [ ] Show plan states: idle, submitting/running, succeeded, failed, unknown.
- [ ] Keep the last successful route visible after a later failure.
- [ ] Show a manual retry control only for `retry_allowed: true`.
- [ ] Include the backend-required retry attempt header/version when retrying.
- [ ] Surface clear English error messages without replacing backend codes.

### SHENG-FE-3 — Chat lifecycle

- [ ] Preserve the existing chat `request_id` for an unresolved message.
- [ ] Display chat attempt state and a manual retry action where allowed.
- [ ] Do not replace the displayed route unless the chat response contains a
  validated revision result and matching metadata.
- [ ] State clearly when an answer is informational and did not change the route.

### SHENG-FE-4 — Runtime status and UI quality

- [ ] Make routing status clear: `mock`, `computed / deterministic`, or
  `computed / agentic`.
- [ ] Display DEM readiness, credential configuration, and returned usage/budget
  only when the backend supplies them.
- [ ] Distinguish NASA imagery errors from API errors.
- [ ] Replace mojibake text such as `Â·`, `â€”`, and `â€¦` with valid UTF-8
  punctuation or plain ASCII.
- [ ] Keep all frontend text in English.

### SHENG-FE-5 — Frontend acceptance tests

- [ ] Same plan action reuses its idempotency key.
- [ ] Stale responses cannot overwrite newer selections.
- [ ] A failed request does not clear a prior successful route.
- [ ] Retry appears only for a retryable failure and never runs automatically.
- [ ] Unknown outcome remains blocked from automatic resubmission.
- [ ] A route changes only after a valid chat revision response.

## Sam — Backend implementation work

### Scope and restrictions

- Own FastAPI request recovery, persistence, provider boundaries, and backend tests.
- Preserve existing success response schemas for route planning and chat.
- Never log, return, or persist OpenAI credentials in request responses, routes,
  chat artifacts, or error details.
- Keep model attempts bounded; do not introduce automatic paid retries.
- Do not change the frontend's Mars coordinate convention.

### SAM-BE-1 — Stable recovery endpoints

- [ ] Confirm `GET /api/v1/routes/requests/{request_id}` implements the shared
  status contract for keyed computed plans.
- [ ] Confirm `GET /api/v1/routes/{route_id}/chat/attempts/{request_id}` implements
  the same contract for chat messages.
- [ ] Return stable state, attempt, retry eligibility, delay, nullable error, and
  nullable update time for every request state.
- [ ] Document any intentionally unsupported status behavior before Sheng relies on it.

### SAM-BE-2 — Idempotency, persistence, and explicit retry

- [ ] Validate `Idempotency-Key` format and bind it to one request body.
- [ ] Prevent simultaneous duplicate work for the same key.
- [ ] Replay the stored successful response for a completed successful key.
- [ ] Persist failed and unknown outcomes across backend restarts.
- [ ] Permit retry only for known eligible failures and only with the current
  backend attempt version.
- [ ] Reject early retries with an actionable JSON response and Retry-After behavior.
- [ ] Ensure timeout/uncertain outcomes remain `unknown` rather than triggering a
  second automatic model call.

### SAM-BE-3 — Error and provider handling

- [ ] Return the existing JSON error envelope for invalid input, missing DEM/profile,
  unavailable route, model configuration failure, provider rejection, budget limit,
  and retry-too-early states.
- [ ] Ensure unhandled exceptions are logged server-side but returned as a safe
  `INTERNAL_ERROR` JSON response.
- [ ] Keep provider/model errors classified without leaking secrets or paths.
- [ ] Do not call the provider during readiness checks.

### SAM-BE-4 — Readiness and A0 status

- [ ] Keep `GET /api/v1/ready` explicit about planning, storage, and credential checks.
- [ ] Keep `GET /api/v1/a0/status` explicit about deterministic/agentic mode,
  configuration presence, model, usage/budget, and last provider failure when available.
- [ ] Distinguish configured credentials from confirmed provider availability.

### SAM-BE-5 — Backend test fixtures for Sheng

- [ ] Provide stable JSON examples for:
  - `plan-running`
  - `plan-succeeded`
  - `plan-failed-retryable`
  - `plan-failed-non-retryable`
  - `plan-unknown`
  - `chat-failed-retryable`
  - `chat-succeeded-revision`
- [ ] Add backend tests for replay, concurrent duplicate calls, explicit retry,
  backend restart retrieval, provider rejection, and unknown outcome behavior.

## Parallel execution schedule

### Day 1 — Contract and fixtures

- Sheng starts `SHENG-FE-1` with local fixtures.
- Sam validates the response contract and produces backend JSON examples.
- Both compare field names, nullability, retry rules, and error shape. No need to
  wait for live endpoint deployment.

### Day 2 — Independent implementation

- Sheng completes `SHENG-FE-2` against fixtures and tests idempotency/state UI.
- Sam completes `SAM-BE-1` and `SAM-BE-2` with API and persistence tests.

### Day 3 — Chat and status

- Sheng completes `SHENG-FE-3` and `SHENG-FE-4`.
- Sam completes `SAM-BE-3` and `SAM-BE-4`.
- Each side runs its own test suite before integration.

### Day 4 — Integration and acceptance

- Point the frontend at Sam's backend.
- Replace only fixture transport calls with real API calls; retain fixtures for tests.
- Run the acceptance matrix below and record failures as separate issues.

## Joint acceptance matrix

| Scenario | Expected result |
| --- | --- |
| Mock route success | Explicit mock label; null metrics; no safety claim. |
| Computed deterministic success | Route metadata and rationale display; computed geometry remains hidden on NASA basemap. |
| Agentic provider rejection | Safe English error; request is recorded; no duplicate automatic request. |
| Retryable failure | Frontend offers manual retry only after backend permits it. |
| Unknown outcome | UI blocks automatic retry and preserves prior route. |
| Backend restart | Existing request status and stored route/chat history remain retrievable. |
| Successful chat revision | New route appears only with validated matching metadata and a parent relationship. |
| NASA imagery failure | Map failure is distinct from API/planning failure. |

## Definition of P0 complete

P0 is complete when a user can understand the active routing/A0 mode, submit one
request safely, see its durable state, recover only through an explicit allowed
retry, keep a previously successful route after failure, and distinguish model,
backend, dataset, and map failures. The team must not claim NASA basemap alignment
or route safety as part of P0.
