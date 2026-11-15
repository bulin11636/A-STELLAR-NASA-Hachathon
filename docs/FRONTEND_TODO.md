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

## P1 — Planning and evidence experience

### Guided planning workflow

- [ ] Present a clear sequence: select Jezero view, choose start/goal, optionally
  add ordered waypoints, choose objective, then plan.
- [ ] Promote the backend-provided in-coverage DEM example as the first computed-mode path.
- [ ] Explain why arbitrary map clicks can be outside planning coverage without
  suggesting that the basemap is registered to the DEM.

### Route result hierarchy

- [ ] Use a compact result summary for source, mode, distance, warnings, and next action.
- [ ] Place detailed provenance, grid policy, worker status, and validation data in
  expandable sections.

### A0 conversation

- [ ] Add English quick prompts for route explanation, `shortest`, `safest`, and
  coordinate-based waypoint edits.
- [ ] Summarize a returned route revision before switching the displayed route.
- [ ] Show route ID, parent relationship, cost/usage when supplied, and a clear
  statement when an answer did not change the route.
- [ ] Keep free-form avoidance polygons, arbitrary policy changes, and unimplemented
  itinerary optimization explicitly unsupported.

### Map and evidence handling

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
