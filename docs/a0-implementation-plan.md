# A0 deterministic route planning: implementation plan

Status: deterministic backend and frontend metadata integration implemented and tested on 2026-11-14; computed browser display acceptance remains pending. See the [actual verification report](a0-verification-report.md). The design and historical baseline below are preserved.
Working branch: `team/a1-a2-sheng-integration`.

The later user request for model-assisted A0, specialist integration, chat-based
route revisions, visible rationale and Docker env-file configuration is tracked
in [the current TODO](TODO.md). The deterministic-only scope below records the
earlier milestone and remains its testable foundation.

This plan records the decisions confirmed on 2026-11-14. It extends the original
mock-integration milestone; it does not describe an already completed planner.
Read the [API addendum](a0-api-contract.md), [verification guide](a0-verification.md)
and [new-chat prompt](a0-new-chat-prompt.md) alongside it.

## Approved outcome

Given Start, Goal and a supported planning mode, use a real Jezero DEM to build
a metric traversability grid, compute an A* route, validate it, persist the route
and its metadata, and expose the result through FastAPI for the frontend.
Deliver the frontend integration needed to retrieve metadata and display a
computed route after map/wire/DEM alignment is established.

Use an ordinary Python coordinator for the main planning pipeline. Live LLM
calls, natural-language mission parsing and autonomous model-driven replanning
are deferred. Preserve the existing optional LangGraph experiment and its tests;
the new deterministic route pipeline must run without LangGraph, LangSmith,
model credentials or network access. Existing `MissionAgent` graph reports and
new persisted route records are different artifacts.

All new or edited repository documentation must be in English. Keep internal
agent IDs and existing import paths unless a concrete integration change needs
an update. Do not rename packages solely to improve presentation.

## Complete public agent names and responsibilities

Use the full public name with a description in documentation and agent-facing
metadata. An ID alone or a short generic title does not explain the system.
These are role definitions, not claims that every listed capability is ready.

| Internal ID | Public name | Responsibility and capability boundary |
| --- | --- | --- |
| A0 | Mission Orchestration and Route Planning Coordinator | Validate mission inputs and available data, dispatch registered analysis tools, request deterministic fusion/planning/validation, preserve provenance, persist results and explain unmet requirements. The first release uses authored Python control flow. |
| A1 | Surface Traversability and Terrain Hazard Agent | Derive slope and supported terrain descriptors from a DEM; supply metric costs, coverage, unknown and blocked masks. Optical obstacle analysis remains an optional future sublayer requiring aligned imagery. |
| A2 | Thermal Environment and Exposure Context Agent | Describe day/night thermal observations, units, times and coverage. Existing DN conversions are prototype heuristics; calibrated temperature, exposure or route constraints require separate validation. |
| A3 | Radiation Exposure and Mission Dose Assessment Agent | Evaluate explicitly configured dose scenarios against a mission duration and user-supplied budget, retaining assumptions and uncertainty. Historical RAD inspection is separate from a Jezero dose-equivalent model. |
| A4 | Geological Context and Science Opportunity Agent | Associate source-attributed sampling POIs with regional geology, retain ambiguity and explain scientific relevance. Priority scoring needs a documented rubric. |
| A6 | Rover Traverse and Observation Evidence Agent | Normalize historical rover positions and segments, compute supported proximity measures, and attach verified observation references. Historical traversal does not establish astronaut safety. |

A5 remains merged into A1; do not create an empty A5 package or an additional
LLM agent. The data catalog, cost fusion, A* planner and route validator are
shared deterministic services, not extra model agents.

## Committed starting point and current work

The bullets below describe committed baseline `a105e51`, not a guarantee that
the current working tree is unchanged. Remote refs and local in-progress work
must be reconciled as described in the
[frontend integration handoff](a0-frontend-integration.md). On 2026-11-14, remote
integration/frontend refs pointed to `4b78b6a` (acquisition handoff); additional
uncommitted A0 and frontend metadata implementation existed locally. Inspect
and verify that work before deciding which functionality remains to implement.
The user confirmed development was paused because remote updates appeared.
Resume this partial implementation after remote reconciliation; do not treat
the handoff as authorization to replace it with a fresh implementation.

- `app.coordinator.mission.MissionCoordinator` returns a mock Start/Goal line.
- `app.coordinator.agent.MissionAgent` is an optional LangGraph evidence loop;
  its route tools report unmet prerequisites, not a computed route.
- A1's adapter returns a prototype slope artifact. Its canonical planning grid
  and mask fields remain unavailable. Audit its CRS, metric derivatives and
  NoData handling before using any output for planning.
- A2 remains a prototype. A3 supports documented scenarios; A4/A6 can use
  prepared, provenance-checked evidence when available.
- Frontend `useRoutePlanner.ts` rejects computed routes while coordinate
  validation is false. `marsCoordinates.ts` and `routeOverlay.ts` currently use
  an explicit mock-only adapter. Removing a guard does not validate coordinates.
- There is no persistent route retrieval endpoint yet.

## Local input policy

The user keeps large inputs outside Git at `~/nasa/project/dataset`:

| Purpose | Existing filename |
| --- | --- |
| Candidate CTX DEM | `M20_JezeroCrater_CTXDEM_20m.tif` |
| Candidate high-resolution DEM | `JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif` |
| Candidate regional mosaic | `NES_JEZ_MID_DEM_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018.tif` |
| Day thermal mosaic | `Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif` |
| Night thermal mosaic | `THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018.tif` |

Filenames do not establish CRS, units, valid resolution or suitability. Inspect
headers and bounded windows; never read a global raster fully into memory just
to select an ROI. Choose one small, connected ROI supported by inspected data,
then record its exact bounds, source window, resolution and valid demo endpoints.
Select the DEM on verified suitability rather than filename resolution claims.

Add a documented host configuration mechanism for the external dataset root
and selected DEM/ROI. Suggested names are `A_STELLAR_DATASET_DIR` and
`A_STELLAR_PLANNING_PROFILE`; they do not exist merely because this plan names
them. A local profile can live under ignored `data/cache/a0/`; tracked examples
must use placeholders or portable relative paths, not this user's absolute path.
Paths resolve relative to the profile or a documented dataset root, not CWD.

The user is downloading A3/A4/A6 separately. Check availability when executing
the implementation; do not assume the downloads finished or depend on a
temporary `/tmp` helper from an earlier chat. Keep these sources optional for
terrain-only routing. No request handler or default test may download data.
Keep raw inputs in place and generated grids/reports in ignored `data/` folders.

## Implementation sequence

### 1. Establish geometry and a canonical grid

Inspect the selected DEM's datum/body, radius or ellipsoid, latitude convention,
horizontal and vertical units, affine transform, masks, scale/offset and footprint.
Do not substitute Earth EPSG:4326, a generic Mars radius or degrees-as-metres.
Use a justified local metric grid with recorded source and target CRS and an
explicit transform to `MARS_2000_PLANETOCENTRIC_EAST_360_V1`.

Record source and output pixel sizes. Upsampling never creates new source
detail. Handle rectangular pixels correctly; rotated/skewed transforms need a
supported reprojection or an explicit rejection. Derivative stencils require
valid neighboring samples; NoData, nonfinite values, unsupported edges and
unknown coverage must not become low-cost cells.

Produce stable references to elevation, slope, coverage, unknown and blocked
masks plus traversability costs and complete geospatial metadata. Include a
halo for derivatives where needed and report the actual cropped planning area.

### 2. Implement cost fusion and bounded A*

Use eight-connected movement with physical metric edge lengths and prohibit
diagonal corner cutting. Unknown and hard-blocked cells are impassable.
Configure and record the slope threshold as an explicit research/demo policy;
an existing prototype's 15-degree default is not a certified safety limit.

- `shortest`: minimize planar metric path length over allowed cells.
- `safest`: minimize a documented nonnegative terrain-penalized distance over
  the same allowed cells. This label preserves the existing API enum and does
  not establish physical safety. Record the cost formula, weights and units.

Use an admissible heuristic consistent with the chosen minimum edge cost;
check optimality against an independent Dijkstra implementation on small grids.
Bound grid allocation, expanded nodes and elapsed work. Move blocking raster
and planning computation outside the event loop. Do not assume cancelling an
async wrapper terminates native work or a worker thread.

Thermal/radiation values without compatible units, temporal meaning and spatial
support must remain contextual results rather than invented per-cell costs.
Missing optional evidence does not silently become a passing constraint. A
terrain-only route can still be computed with explicit unassessed constraints.

### 3. Validate geometry and endpoints

Check the full route against ROI, coverage, unknown/blocked masks, connectivity
and active policy. Validate endpoint connectors as well as grid-center edges.
Preserve exact requested Start and Goal in the public polyline; never append
unvalidated connectors merely to satisfy the schema. Distinct endpoints in the
same cell require a validated segment. Requests with identical endpoints keep
the existing 400 behavior. No smoothing may cross unvalidated terrain.

Verify wire-to-grid-to-wire round trips and map-to-wire-to-DEM registration
using recorded source information and control fixtures with justified tolerances.
An inverse-transform round trip alone does not establish correct registration.
Do not flip `COORDINATE_CONVENTION_VALIDATED` without evidence and adapter tests.
If map alignment remains unresolved, retain the display guard, expose the
validated API result where appropriate, and report frontend acceptance as pending.

### 4. Persist and expose results

Implement the [API addendum](a0-api-contract.md), including durable local storage
and `GET /api/v1/routes/{route_id}`. Save records atomically and support retrieval
after creating a fresh application instance. Serve registered IDs; do not expose
an arbitrary filesystem path endpoint. Keep public source/artifact identifiers
separate from private local paths.

Return `source: "computed"` only after grid, A*, route validation and persistence
succeed. In configured computed mode, failure must never silently fall back to
a mock line. Preserve an explicit mock mode for existing integration coverage.

### 5. Integrate the frontend and run acceptance checks

First follow the [frontend integration handoff](a0-frontend-integration.md):
fetch and inspect current remote/frontend revisions, preserve local work and
extend the latest existing UI/client rather than an older baseline. Reuse any
in-progress metadata client and generated contracts after checking them.

Keep browser NASA tile access unchanged. Add typed retrieval/metadata decoding,
handle unavailable results, retain request cancellation and stale-response
protection, and distinguish mock and computed research results in the UI.
Show distance, source/version, resolution, policy and relevant caveats. Unknown
time/risk stays null. Use complete public agent names when presenting agents.

Run the [verification guide](a0-verification.md). Produce a run report that
separates synthetic correctness, real-data API verification, map registration
and browser rendering. Do not claim completion from existing scripted A0 tests.

## Completion criteria

All of the following are required for the complete requested outcome:

1. A validated metric grid derived from one real local DEM and a recorded ROI.
2. Correct, bounded A* routing and independent route validation with meaningful
   negative cases and no mock fallback in computed mode.
3. A persisted real-data result and metadata, retrievable by route ID after restart.
4. A documented compatible API extension with matching frontend types/decoders.
5. Verified map/wire/DEM alignment and computed route display, or an explicit
   statement that this acceptance item remains incomplete.
6. Passing applicable backend/frontend checks and an English verification report
   listing exact commands, artifacts, assumptions and any remaining blockers.

Do not modify the optional LangGraph experiment merely to make its old blocked
demonstration appear to generate routes. Live-model testing is outside this scope.
