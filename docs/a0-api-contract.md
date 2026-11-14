# A0 route persistence and API addendum

Status: implemented and tested on 2026-11-14; see the [verification report](a0-verification-report.md). Scope: deterministic terrain-based A* routing. Computed map registration remains unverified.

The [original protocol](A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md) remains the
authority for existing request fields, coordinates, response fields and errors.
This addendum defines the user-approved next milestone: computed routes,
persistent metadata, retrieval and the corresponding frontend integration.
The original document's F1.5 exclusions describe the earlier mock milestone.
Implement this addendum in backend schemas, frontend types/decoders, tests and
OpenAPI together. Do not silently change existing field meanings.
Reconcile the [current frontend](a0-frontend-integration.md) before making those
changes, including local in-progress metadata contracts and clients. Reuse the
existing API transport and preserve current selection/cancellation behavior.

## Endpoint contract

`GET /api/v1/regions` also supplies nullable `planning` information for a ready
computed grid: `roi_id`, `bounds` (`west/east/south/north` in wire degrees),
`resolution_m` (positive x/y metres), and nullable `example_request` with the
existing `PlanRouteRequest` shape. Mock/unavailable regions return null. The
inspected CTX demo window advertises its verifier endpoint cells converted by
the actual grid transform; other windows do not inherit those endpoints.
These fields support discoverable coverage and do not certify map alignment,
endpoint connectivity or environmental safety. Restart older servers to expose
the new information; clients tolerate its absence without guessing bounds.

The current computed implementation also advertises `source_bounds`,
`dynamic_windowing`, `max_grid_cells` and nullable `regional_example_request`.
The latter uses the same request shape with explicit source-derived regional
demo endpoints; validate it against source bounds rather than the seed window.
`PlanRouteRequest.waypoints` is optional, ordered, and limited to 16 required
coordinates. Returned/persisted geometry must retain every waypoint in order.
See [regional verification](regional-verification.md) for adaptive-resolution
semantics and the [chat guide](a0-agent-chat.md) for revision endpoints.

| Method and endpoint | Target behavior |
| --- | --- |
| `GET /api/v1/health` | Existing health response; no scientific readiness claim. |
| `GET /api/v1/ready` | Local planning/key-presence checks; HTTP 200 ready or 503 not ready, without contacting the provider. |
| `GET /api/v1/regions` | Retain existing fields; permit `routing_mode: "mock"` or `"computed"`. Advertise availability from actual configured readiness. A computed-mode region without valid prerequisites has `routing_available: false`. |
| `POST /api/v1/routes/plan` | Existing request and success response shape. In configured computed mode, compute, validate and persist before returning success. |
| `GET /api/v1/routes/{route_id}` | New endpoint returning the persisted route result and its metadata. |

The backend selects an explicitly configured routing mode; no extra mandatory
request field is introduced. A fresh unconfigured environment can retain mock
mode for compatibility. Mock mode must remain labeled. Computed mode must not
return mock success when a grid, transform or route is unavailable.

## Planning response

Keep `PlanRouteResponse` fields and the exact request Start and Goal. `source`
already permits `mock | computed`; successful terrain planning uses `computed`.
`metrics.distance_m` is the validated polyline's metric-grid planar length,
including endpoint connectors. State this distance convention in metadata;
do not describe it as a terrain-following 3D distance. Keep
`estimated_time_min` null unless an explicit supported speed model is recorded.
Keep `risk_score` null unless a separately defined normalized model is implemented
and tested; the A* objective value is not automatically a normalized risk score.

Return nonempty research limitations for computed routes, including unassessed
thermal/radiation/imagery constraints where relevant. A successful terrain route
does not mean the complete mission or every specialist constraint passed.

## Retrieval response

Return HTTP 200 with this object:

```text
StoredRouteResponse {
  result: PlanRouteResponse,
  metadata: RouteMetadata
}
```

`result` must equal the planning response associated with `route_id`. The frontend
can immediately draw the POST result when coordinate validation permits, then
fetch metadata by its ID. A later browser session can use GET alone to reload a
stored route. Do not introduce separate route-list, tile or raw-file endpoints
unless a concrete integration need arises.

### Required metadata

Implement typed nested schemas, not an unvalidated dictionary. All fields below
are required; nullable fields explicitly represent unknown values.

| Field | Type and meaning |
| --- | --- |
| `schema_version` | String, initially `"1"`. |
| `route_id` | String matching the URL and `result.route_id`. |
| `created_at` | ISO 8601 UTC timestamp with timezone. |
| `request` | Original validated `PlanRouteRequest`. |
| `coordinator` | Object with `agent_id: "A0"`, full public name and implementation version. |
| `scope` | Object with `region_id`, stable `roi_id`, `dataset_version` and longitude/latitude bounds with named west/east/south/north fields. |
| `sources` | Array of dataset IDs, source URLs (nullable if unknown), input filenames, content hashes, instrument/mission when known, acquisition time when known, and provenance record IDs. Do not fabricate source identity from a filename. |
| `grid` | Object with `grid_id`, source/planning CRS definitions, wire convention, affine transform (document coefficient order), width/height, source resolution, planning x/y resolution in metres, vertical units/scale/offset, NoData representation and mask artifact IDs. Unknown source details remain null with warnings; facts required for planning must be verified. |
| `policy` | Policy/version ID, slope threshold in degrees, unknown handling, connectivity, corner-cutting rule, endpoint rule, mode-specific cost formula and parameters, and the run's grid/node/time limits. |
| `planner` | Object with `algorithm: "astar"`, implementation version, heuristic, objective cost and units, expanded nodes, elapsed milliseconds and distance convention. |
| `validation` | Object with `status: "passed"` for computed successes, validator version, checks performed, transform/control fixture IDs, tolerances and map alignment status (`verified` or `unverified`). Backend route validation and browser alignment are separate checks. |
| `workers` | Array of requested specialist IDs, complete public names, statuses, evidence kinds, dataset/artifact IDs, warnings and unassessed constraints. Do not claim an uninvoked specialist ran. |
| `artifacts` | Object mapping logical roles to stable artifact IDs and hashes. Large grids stay on disk; public metadata does not contain raw arrays or private paths. |
| `warnings` | Array of plain-English limitations, unresolved assumptions and unavailable optional evidence. |

Input SHA-256 identifies exact locally used content; it is not proof of
publisher authenticity. Compute/reuse a source digest outside per-request work,
record the source identity, and detect changed inputs before reusing cached grids.
Avoid hashing a multi-GB raster on every route request.

Keep detailed private source paths, build logs and local artifact references in
an internal provenance record. Public metadata uses logical identifiers and
filenames. Malformed or nonfinite stored values must not be served as success.

## Error additions

Use the existing `{"error": {"code", "message", "details"}}` envelope.

| HTTP | Code | Condition |
| --- | --- | --- |
| 400 | `OUTSIDE_PLANNING_COVERAGE` | Start or Goal lies outside the configured valid planning footprint. |
| 400 | `ENDPOINT_NOT_TRAVERSABLE` | An endpoint or its required connector intersects a blocked or unknown area. |
| 404 | `ROUTE_NOT_FOUND` | No complete stored record exists for the supplied valid route ID. |
| 422 | `VALIDATION_ERROR` | Existing structural input validation, also used for malformed route IDs. |
| 422 | `NO_PATH` | Valid endpoints cannot be connected under the selected grid and policy. |
| 503 | `PLANNING_UNAVAILABLE` | Computed mode lacks readable/validated data, CRS or a canonical grid. |
| 503 | `PLANNING_LIMIT_EXCEEDED` | Documented grid/node/time limits prevent completing this request. |
| 500 | `ROUTE_STORAGE_ERROR` | A validated result could not be atomically persisted. Do not return planning success. |
| 500 | `ROUTE_RECORD_INVALID` | A published stored record is corrupt or internally inconsistent. |

Existing `INVALID_ROUTE`, `UNSUPPORTED_COORDINATE_SYSTEM`, `UNKNOWN_REGION` and
general errors keep their original meanings. Messages do not expose stack
traces, secrets or private paths. Missing/incomplete unpublished records are
not a successful route.

## Persistence rules

Use an ignored configurable output root, defaulting to
`data/processed/routes/<route_id>/`. A simple file-backed store is sufficient;
no database or separate service is required for this milestone.

- Allocate opaque server-generated IDs and validate the ID format before lookup.
  Never accept a client-selected filesystem path or resolve traversal segments.
- Stage response, metadata and referenced run artifacts privately, validate the
  complete record, then publish an atomic completion marker or directory rename.
- Do not overwrite another run's artifacts. Concurrent requests are isolated.
- A fresh app instance must retrieve the same result from the configured store.
- Readers reject malformed records, ID mismatches and missing/tampered required
  artifacts. Never expose a half-written record as a complete computed result.
- Keep generated results out of Git. Tests use temporary output roots.

The local file store targets this developer prototype. Authentication, hosted
storage, task queues and multi-host coordination are outside this change.

## Implemented configuration and contracts

`A_STELLAR_ROUTING_MODE` selects `mock` (default) or `computed`.
`A_STELLAR_PLANNING_PROFILE` names a trusted local JSON profile. Relative DEM
paths resolve against `A_STELLAR_DATASET_DIR` when set, otherwise against the
profile directory. `A_STELLAR_ROUTE_STORE` optionally supplies an absolute local
output directory. No handler downloads inputs. Grid construction and source
hashing occur at application construction; requests reject a changed source
fingerprint until the grid is rebuilt.

`app.contracts.routes` defines the nested persisted schemas, with finite values,
UTC timestamps and cross-record identity/artifact checks. Run
`python -m app.planning.export_contract` from `backend/` to regenerate the existing
browser metadata types and serialization schema. A backend regression checks
for contract drift. Retrieval verifies completion manifests and required file
hashes. The frontend also checks ID, request, source version, mask/artifact
references and agreement with the POST result, independent of JSON key order.

Current computed records always report `validation.map_alignment: "unverified"`.
Source URLs, instrument, mission and acquisition time remain null for the
unreceipted local DEM rather than being inferred from its filename. The real
verification report explains the metadata-backed metre interpretation and
source-radius discrepancy.
