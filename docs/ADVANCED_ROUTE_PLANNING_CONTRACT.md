# Quick and Advanced Route Planning Contract

## Ownership

- **Sheng:** owns the interaction flow, typed client, request lifecycle, tests, and English user-facing text.
- **Sam:** owns request validation, A0 context handling, policy validation, persistence, API tests, and safe errors.

This document is the shared implementation contract for P0. Quick mode must
continue to work if Advanced mode or A0 is unavailable.

## Product modes

### Quick Route Planning

Quick mode has exactly these inputs:

1. Start coordinate.
2. Goal coordinate.
3. Route objective: `safest` or `shortest`.

It sends one existing route request and never sends an A0 chat request.

```text
POST /api/v1/routes/plan
```

The UI label is **Shortest**, not “Fastest”, because the supported backend
objective is shortest path cost, not validated travel time.

### Advanced Route Planning

Advanced mode exposes only typed, bounded controls. It must not present a UI
control for unsupported arbitrary slope limits, arbitrary polygons, thermal
thresholds, radiation limits, or safety certification.

| Field | Wire value | Validation | Effect |
| --- | --- | --- | --- |
| Start / Goal | `MarsCoordinate` | Existing coordinate contract | Base route input |
| Route objective | `safest` / `shortest` | Existing enum | Base route input |
| Required waypoints | ordered `MarsCoordinate[]` | 0–16; consecutive stops differ | Mandatory intermediate stops for the base route, visited in displayed order |
| Analysis focus | `terrain`, `science`, `operations` | 1–3 unique values | A0 explanation/revision context only; never changes terrain cost directly |
| Allow supported revision | boolean | Required | Controls whether A0 may propose a supported route revision |
| Additional requirements | plain text | Trimmed 1–1,600 characters | A0 context only; host policy remains authoritative |

## Advanced user flow

```text
Configure Advanced parameters
        ↓
Plan base route (same typed route API as Quick mode)
        ↓
Base route succeeds and is persisted
        ↓
Send A0 chat request with Advanced context and user requirements
        ↓
Show explanation or validated route revision
        ↓
Replace displayed route only if backend returns result + matching metadata
```

The UI must disclose that **Plan and Ask A0** can make one route request plus
one A0 request. It must never automatically retry a model request.

If the base plan fails, do not send chat. If chat fails, preserve the base
route and show its request state/error.

## API contract

### 1. Base route request — unchanged

Both modes use the existing request unchanged:

```json
{
  "region_id": "jezero",
  "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  "start": { "longitude": 77.42, "latitude": 18.44 },
  "goal": { "longitude": 77.48, "latitude": 18.46 },
  "mode": "safest",
  "waypoints": [
    { "longitude": 77.45, "latitude": 18.45 }
  ]
}
```

For computed routing, Sheng sends an `Idempotency-Key`. Sam retains the
existing keyed-request recovery behavior.

### 2. Chat request — add optional `advanced_context`

Sam adds this optional object to the existing chat request schema. Existing
clients that send only `message` and `request_id` remain valid.

```json
{
  "message": "Prefer an explanation of terrain limitations near the required stop.",
  "request_id": "advanced_chat_1234567890",
  "advanced_context": {
    "schema_version": "1",
    "interface_mode": "advanced",
    "route_objective": "safest",
    "required_waypoints": [
      { "longitude": 77.45, "latitude": 18.45 }
    ],
    "analysis_focus": ["terrain", "science"],
    "allow_supported_revision": true
  }
}
```

### 3. Backend validation rules — Sam

- `advanced_context` is optional; when absent, retain current chat behavior.
- Reject unknown fields in `advanced_context`.
- Require `schema_version: "1"` and `interface_mode: "advanced"`.
- Validate route objective, coordinate convention, finite coordinates, maximum
  16 waypoints, and non-duplicated consecutive stops.
- Require `analysis_focus` to be a unique non-empty subset of:
  `terrain`, `science`, `operations`.
- Verify `route_objective` and `required_waypoints` exactly match the persisted
  parent route request. A mismatch returns structured HTTP 422; the chat
  context cannot silently rewrite the route that the user is discussing.
- Treat `additional requirements` as the existing bounded `message` field;
  do not add a second free-text field.
- When `allow_supported_revision` is false, return explanation only and never
  attach a route revision.
- When it is true, A0 may propose only host-supported changes. Python policy,
  deterministic planner, independent validation, and persistence remain the
  only authority for a revision.
- Do not turn analysis focus or free text into a terrain safety score, a policy
  override, an arbitrary avoidance geometry, or an unsupported constraint.

### 4. Response and recovery

The existing `ChatResponse` response remains unchanged. A revision is valid
only when `result` and `metadata` are both present, validate together, and
metadata has `parent_route_id` equal to the route discussed.

Request recovery stays unchanged:

```text
GET /api/v1/routes/requests/{idempotency_key}
GET /api/v1/routes/{route_id}/chat/attempts/{request_id}
```

## Sheng implementation

### UI structure

```text
Route Planning
  [Quick] [Advanced]

Quick
  Start, Goal, Safest/Shortest, Plan Route

Advanced
  Start, Goal, Safest/Shortest
  Required waypoints: add from map or coordinates, reorder, remove
  Analysis focus checkboxes
  Allow A0-supported revision checkbox
  Additional requirements textarea
  Plan and Ask A0
```

All visible UI strings are English. The selected mode is local UI state and
does not change the Mars coordinate contract.

### Required waypoint interaction

Advanced mode adds a **Required Waypoints** section between Start/Goal and the
route objective.

```text
Required Waypoints (0/16)
[Add waypoint from map] [Add coordinate]
1. Longitude 77.450000 E, Latitude 18.450000  [Move up] [Move down] [Remove]
2. Longitude 77.460000 E, Latitude 18.455000  [Move up] [Move down] [Remove]
```

- **Add waypoint from map** changes the map click action to `Pick Waypoint`.
  Each accepted click appends one waypoint and remains in that mode until the
  user returns to Inspect or selects another action.
- **Add coordinate** uses named longitude/latitude inputs in the existing Mars
  API convention: east longitude `[0, 360)`, planetocentric latitude `[-90, 90]`.
- The ordered list is authoritative. The user can move a waypoint up/down or
  remove it before planning.
- The UI displays waypoints as `W1`, `W2`, … on the map and in the route
  preview. Start and Goal remain distinct markers.
- A maximum of 16 required waypoints is enforced before a request is sent.
- Consecutive duplicate stops are rejected locally. The backend repeats the
  same validation and preserves the exact visit order in its response.
- A required waypoint is a mandatory visit, not a soft preference and not an
  automatically optimized stop order.

### Sheng request behavior

- Quick: submit only `POST /routes/plan`.
- Advanced: submit the same base route request, await success and computed
  metadata, then submit chat with `advanced_context`.
- Disable **Plan and Ask A0** until Start, Goal, at least one analysis focus,
  and non-empty additional requirements are present.
- Display a clear notice that Advanced mode may use an A0 request and consume
  configured API budget.
- Keep the last successful route during all later failures.
- Present a manual retry only when the backend attempt status permits it.

## Tests

### Sheng unit/integration tests

- Quick mode serializes only the existing plan request and sends no chat call.
- Advanced mode validates controls and serializes the exact `advanced_context`.
- Advanced mode does not chat after failed/unavailable base planning.
- Advanced mode sends chat only after a successful persisted computed route.
- Chat failure preserves the base route.
- A valid revision replaces the base route; malformed/mismatched revision does not.
- Retry UI follows backend `retry_allowed` and never auto-retries.

### Sam tests

- Existing chat request remains compatible without `advanced_context`.
- Valid advanced context persists and is supplied to A0 in typed form.
- Unknown field, invalid focus, invalid coordinate, or stored-route mismatch
  returns the existing structured validation error.
- `allow_supported_revision: false` cannot produce a revision.
- Agentic failure, retry, restart retrieval, and duplicate request behavior
  remain safe with advanced context.

## Explicit non-goals

- No browser-side A* planning, LLM call, DEM processing, or hidden OpenAI key.
- No unbounded prompt-driven policy changes.
- No claim that a route is safe, optimal, or geographically registered to the
  NASA basemap.
