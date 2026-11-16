# API guide

The API is served by FastAPI under `/api/v1`. Runtime schemas at `/docs` and
`/openapi.json` are the detailed reference. Backend models live in
`backend/app/contracts/`; generated browser schemas/types live in
`frontend/src/types/`. Deploy compatible frontend and backend contracts together.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Process liveness |
| GET | `/api/v1/ready` | Local data, storage and credential configuration readiness |
| GET | `/api/v1/regions` | Supported region, planning/source bounds and valid example requests |
| GET | `/api/v1/planning/policies` | Versioned mission profiles, resolution choices and limits |
| GET | `/api/v1/planning/registration` | Registration evidence status; no route-wide verification without route applicability |
| POST | `/api/v1/routes/plan` | Create a mock or configured computed route |
| GET | `/api/v1/routes/{route_id}` | Retrieve a computed route and persisted metadata |
| GET | `/api/v1/routes/requests/{request_id}` | Inspect a keyed planning attempt |
| POST | `/api/v1/routes/{route_id}/chat` | Ask about a stored route or propose a supported revision |
| GET | `/api/v1/routes/{route_id}/chat` | Retrieve the route conversation/history |
| GET | `/api/v1/routes/{route_id}/chat/attempts/{request_id}` | Inspect a chat attempt |
| GET | `/api/v1/a0/capabilities` | Inspect configured specialist capabilities without generation |
| GET | `/api/v1/a0/status` | Runtime mode, local allowance and recorded provider observations |
| GET | `/api/v1/map/layers` | Available allowlisted local raster previews and display extents |
| GET | `/api/v1/map/layers/{layer_id}.png` | Render an available bounded raster preview |
| GET | `/api/v1/map/geology` | Source-backed regional geology features when configured |
| GET | `/api/v1/map/nasa/{layer_id}/{resource}` | Bounded same-origin access to allowlisted NASA WMTS resources |

Readiness, capability and status inspection do not call the model. A ready
configuration or successful model-list request does not prove provider credit
or generation access. Creating a route in agentic mode and posting chat can
make metered model requests.

## Plan inputs

`PlanRouteRequest` contains:

| Field | Meaning |
| --- | --- |
| `region_id` | Currently `jezero` |
| `coordinate_system` | `MARS_2000_PLANETOCENTRIC_EAST_360_V1` |
| `start`, `goal` | Named finite `longitude` and `latitude`; endpoints must differ |
| `mode` | `shortest` or terrain-penalized `safest` |
| `waypoints` | Up to 16 intermediate coordinates, visited in the supplied order |
| `mission_profile` | Optional `safest`, `fastest`, `science_priority` or `balanced` |
| `resolution_profile` | Optional `coarse`, `standard` or `fine` |
| `mission` | Optional walking/exposure assumptions and required analyses |

Longitude is east-positive in `[0,360)` and latitude is planetocentric in
`[-90,90]`. Consecutive route stops must differ. Obtain a usable example from
`regions[].planning.example_request`, or the regional example when advertised;
coordinates from a visual map do not guarantee coverage or traversability.

The policy catalog defines each profile's supported objective and limits.
Clients must not invent weights or override a versioned profile's objective.
Actual resolution can be coarser than the requested label under regional limits.

A walking mission can specify speed, dwell per intermediate visit, explicit
exposure duration, scenario radiation budget and required specialist analyses.
See [agents](agents.md#walking-and-exposure-assumptions) for what the estimate
includes and excludes. A missing speed leaves time unknown.

## Results and stored metadata

The plan response contains `status`, `route_id`, region/convention, mode, source,
ordered route geometry, metrics and warnings. Mock responses remain explicitly
mock; they are not observations or validated computed records.

For a computed result, retrieve `/routes/{route_id}` for `{result, metadata}`.
Metadata includes the original request, dataset/source identity, grid and policy,
validation, leg breakdown, rationale, specialist trace, assessment, registration,
artifacts and an optional parent route ID. Verify response identity before applying
metadata or a revision to the currently displayed route.

| Value | Interpretation |
| --- | --- |
| `result.metrics.distance_m` | Measured projected route length in metres |
| `result.metrics.estimated_time_min` | Walking estimate when explicit assumptions permit it |
| `result.metrics.risk_score` | Legacy metric field; do not substitute it for the mission assessment |
| `metadata.assessment.risk_score` | Complete comparable mission index, 0–100; may be null |
| `metadata.assessment.partial_risk_score` | Available-factor index, 0–100; may be null |
| `metadata.assessment.risk_evidence_coverage` | Assessed profile risk weight, 0–100; not spatial coverage |
| `metadata.assessment.assessment_confidence` | Separate evidence-quality score, 0–100 |
| `risk_factors[].risk_score` | Individual assessed factor in 0–1 units |
| `hard_gate_status` | Mission assessment `pass`, `blocked` or `unassessed` |

Optional partial fields support older records through backend validation. Missing
values are not zero. Gate status, confidence and limitations remain important even
when a partial numerical score is shown. These indices are not accident probabilities.

## Chat inputs and revisions

A chat body includes `message` (1–1600 trimmed characters), `request_id` (16–64
letters, digits, underscores or hyphens), and optional typed `advanced_context`.
The response contains the user/assistant message, original route ID, timestamp,
trace and optional usage. An informational response has no revised result.
An accepted revision includes its new result and metadata, with a parent route ID.

Advanced context must match the persisted parent's objective and ordered stops,
not an edited unsent draft. It carries analysis focus and an explicit revision
permission. Explanation-only requests cannot apply a revision. New waypoints
must be recognized source locations, existing stops or explicitly supplied
coordinates; the host rejects invented positions. Mission-profile changes need
a new typed plan rather than a free-text objective override.

## Request recovery

Computed plans may carry an `Idempotency-Key`. The frontend uses a fresh key for
a new intended action, and retains it while an outcome is unresolved. Chat uses
its body `request_id`. Reuse a key only with the same frozen input.

| State | Appropriate action |
| --- | --- |
| `running` | Check status; do not automatically submit another generation |
| `succeeded` | Recover the saved response using the original request |
| `failed` | Inspect the cause; manually retry only when `retry_allowed` permits it |
| `unknown` | Treat the outcome as uncertain; inspect/recover rather than automatically executing again |

For an eligible manual retry, preserve the original body/key and send
`X-A-Stellar-Retry-Attempt` with the current `attempt` returned by status. The
server advances a version once; competing or stale retries are rejected.
Honor `retry_after_seconds` and refresh status before enabling retry. Replaying a
saved successful result does not generate a new model response.

Cancellation or a lost HTTP response does not prove that backend computation or
provider generation stopped. Published results and attempt records persist across
ordinary restart. Do not delete claims or accounting state as a recovery strategy.

## Errors

An error envelope contains an `error` object with `code`, `message` and
`details`. Inspect the code and structured details, not only the HTTP status. In particular, a backend HTTP 503
can describe a provider HTTP 400/429 or a rejected proposal from an HTTP 200
response. Coverage/search errors, application allowance, provider credit, malformed
proposals and uncertain outcomes need different remedies. See
[provider troubleshooting](provider-troubleshooting.md).
