# Frontend Improvement TODO

This backlog covers the existing React/OpenLayers frontend. User-facing product
text, status messages, controls, errors, and code comments introduced for these
tasks must remain in English.

## Guardrails

- Keep the Mars wire convention explicit: `MARS_2000_PLANETOCENTRIC_EAST_360_V1`.
- Do not expose OpenAI credentials in browser code.
- Keep mock, deterministic computed, and agentic computed outcomes visibly distinct.
- Do not render computed route geometry over the NASA basemap until independent
  NASA WMTS/wire/DEM registration evidence has been accepted.
- Do not describe a route as safe, validated, recommended, or optimal.
- Preserve the existing typed API client, cancellation, stale-response protection,
  and backend error envelope handling.

## P0 — Demo-blocking reliability and clarity

### Request lifecycle and recoverable failures

- [ ] Integrate the computed-plan request status endpoint:
  `GET /api/v1/routes/requests/{request_id}`.
- [ ] Integrate the chat-attempt status endpoint:
  `GET /api/v1/routes/{route_id}/chat/attempts/{request_id}`.
- [ ] Show `running`, `succeeded`, `failed`, and `unknown` request states in the UI.
- [ ] Show retry eligibility and `retry_after_seconds`; never retry model calls automatically.
- [ ] Send an `Idempotency-Key` for a computed planning request and retain it until
  the request outcome is resolved.
- [ ] Preserve the last successful route when a later plan or chat request fails.
- [ ] Add focused tests for replay, conflict, eligible retry, and unknown outcomes.

### Runtime state and mode disclosure

- [ ] Make routing mode prominent: `mock`, `computed / deterministic`, or
  `computed / agentic`.
- [ ] Show whether the configured DEM, route store, and model credentials are ready.
- [ ] Keep model configuration presence separate from confirmed provider access.
- [ ] Display request count and estimated/reserved cost only when returned by the backend.
- [ ] Use clear action-oriented errors for an unreachable API, a missing dataset,
  invalid planning profile, missing credentials, and provider rejection.

### Text and encoding quality

- [ ] Replace mojibake characters such as `Â·`, `â€”`, and `â€¦` with valid UTF-8
  punctuation or plain ASCII equivalents.
- [ ] Keep every new and updated frontend string in English.
- [ ] Standardize status vocabulary across planner, map, A0 status, and chat panels.

## P1 — Planning and evidence experience

### Guided planning workflow

- [ ] Present a clear sequence: select Jezero view, choose start/goal, optionally
  add ordered waypoints, choose objective, then plan.
- [ ] Promote the backend-provided in-coverage DEM example as the first computed-mode path.
- [ ] Explain why arbitrary map clicks can be outside planning coverage without
  suggesting that the basemap is registered to the DEM.
- [ ] Keep a single visible primary action and disable it with an actionable reason.

### Route result hierarchy

- [ ] Use a compact result summary for source, mode, distance, warnings, and next action.
- [ ] Place detailed provenance, grid policy, worker status, and validation data in
  expandable sections.
- [ ] Keep mock metrics visibly null and label mock routes as non-safety-validated.
- [ ] Surface computed rationale, limitations, evidence IDs, and unassessed specialist inputs.
- [ ] Preserve metadata consistency checks between POST results and stored-route retrieval.

### A0 conversation

- [ ] Add English quick prompts for route explanation, `shortest`, `safest`, and
  coordinate-based waypoint edits.
- [ ] Summarize a returned route revision before switching the displayed route.
- [ ] Show route ID, parent relationship, cost/usage when supplied, and a clear
  statement when an answer did not change the route.
- [ ] Keep free-form avoidance polygons, arbitrary policy changes, and unimplemented
  itinerary optimization explicitly unsupported.

### Map and evidence handling

- [ ] Distinguish NASA imagery/tile failures from API failures.
- [ ] Maintain the computed-geometry display guard until map registration is verified.
- [ ] Show coverage, provenance, uncertainty, unavailable state, and source links for
  evidence layers without creating client-side hazard or temperature maps.

## P2 — Polish, accessibility, and release confidence

- [ ] Improve responsive layout for narrow screens and long route metadata.
- [ ] Audit keyboard navigation, focus order, labels, `aria-live` updates, and color contrast.
- [ ] Add a one-click demo reset using fixtures only; do not impersonate scientific data.
- [ ] Add Playwright workflows for mock success, computed success, offline API, missing
  credentials, invalid metadata, request recovery, and Vite proxy failure.
- [ ] Add browser acceptance checks for map fitting and nearby-stop usability.
- [ ] Publish a short English demo script for judges and project contributors.

## Suggested delivery order

1. P0 request lifecycle, runtime state, and text/encoding fixes.
2. P1 guided planning and result hierarchy.
3. P1 A0 conversation and evidence presentation.
4. P2 responsive, accessibility, and browser acceptance coverage.

## Explicit non-goals for this frontend backlog

- Browser-side DEM processing, A* search, science fusion, or direct LLM calls.
- Displaying a computed route on the NASA basemap before registration validation.
- Treating A2 visual mosaics, A3 historical scenarios, A4 geology, or A6 rover
  history as an automatic astronaut-safety assessment.
