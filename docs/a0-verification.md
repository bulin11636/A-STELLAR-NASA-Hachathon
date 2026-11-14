# A0 implementation verification and acceptance

Status: verification procedure with an implemented real-data command below.
Actual 2026-11-14 outcomes are in the [verification report](a0-verification-report.md).
The complete outcome remains pending map registration and browser acceptance.
Use the [implementation plan](a0-implementation-plan.md) and
[API addendum](a0-api-contract.md) as the target.

## Establish the baseline

Work in `/home/sam/nasa/repo/A-STELLAR` on
`team/a1-a2-sheng-integration`. Read applicable `AGENTS.md` instructions and
inspect the working tree before changing files. Preserve unrelated changes and
the handoff documents, even when they have not been committed.

Refresh remote refs and follow the
[frontend integration handoff](a0-frontend-integration.md) before choosing a
baseline. Record HEAD, the remote integration/frontend revisions, their source
diffs and relevant modified/untracked local files. If implementation already
exists in the working tree, inspect and test it before filling remaining gaps.
Keep baseline failures distinguishable from regressions in the combined work.
The user paused local development when the remote changed. Reconcile that
update with the existing partial implementation before adding more features,
then verify existing functionality and implement only the remaining gaps.

Inspect actual package versions and installed environments before installation.
The original setup is Windows-oriented; use `.venv/bin/python` and `npm` on
Linux. Existing dependency pins may need compatibility checks on this machine;
do not silently upgrade the whole dependency graph to make an install succeed.
Report baseline failures separately from new failures.

Example baseline/check commands, when the corresponding environment exists:

```bash
cd /home/sam/nasa/repo/A-STELLAR/backend
.venv/bin/python -m pytest -q

cd /home/sam/nasa/repo/A-STELLAR/frontend
npm test
npm run build
```

The current environment is not guaranteed to have `.venv`, installed Node
dependencies, rasterio or downloaded A3/A4/A6 inputs. Install needed dependencies
through the normal permission flow when required; document the commands and
versions. The new deterministic runtime needs raster/geometry packages but must
not require LangGraph or model credentials. Test its import boundary in an
isolated environment or subprocess where those optional imports are unavailable.

## Synthetic algorithm and geometry checks

Use small generated fixtures with known answers; do not check in large rasters.

| Area | Required meaningful checks |
| --- | --- |
| DEM ingestion | Flat plane and known incline; rectangular pixel spacing; vertical scaling; NaN/NoData holes; derivative boundary/halo behavior; supported reprojection or rejection of skewed input; incompatible body/CRS rejection. |
| Coordinates | Recorded wire/grid round trips within justified tolerance, positive-east longitude and planetocentric latitude, known source/control registration, correct row/column order and bounds. Earth conversion and a self-consistent wrong transform must not pass as verification. |
| Search correctness | Obstacle detour, disconnected goal, corner-cut rejection, deterministic tie behavior, start/goal in one cell, boundary endpoints, and independent Dijkstra cost comparison on small grids. |
| Cost policy | `shortest` length objective; terrain-penalized `safest` objective; nonnegative costs; admissible heuristic; a fixture where the terrain penalty changes the preferred route. |
| Route validation | Validate every segment and endpoint connector; reject paths crossing masked cells, leaving the ROI or changing source/version. |
| Resource limits | Bound allocation/search; missing or unreadable sources fail clearly; bounded planning work does not stall unrelated health requests. |

Check results against independent expected values or invariants. A test that
only repeats the implementation's formula is insufficient evidence of correctness.

## API and persistence checks

1. Preserve original health, input validation, coordinate and explicit mock tests.
2. POST a synthetic-but-georeferenced terrain request to exercise the real
   planner; identify the synthetic source in metadata rather than NASA data.
3. Verify `source: "computed"` requires A*, validation and committed storage;
   check exact endpoints, finite planar distance and null unsupported metrics.
4. GET the returned route ID and compare the stored result with the POST result.
   Validate every required metadata section against typed schemas.
5. Recreate the app/store reader and GET again to demonstrate restart persistence.
6. Cover missing IDs, malformed/traversal IDs, corrupt records/artifacts,
   incomplete writes, concurrent isolation and unwritable storage.
7. In computed mode, exercise unavailable grid, out-of-coverage/blocked endpoints,
   no path and exhausted limits; check documented errors and no mock fallback.
8. Run with A2/A3/A4/A6 unavailable. Terrain routing may succeed, but those
   constraints must remain explicitly unassessed.

Default test suites must be offline, use temporary stores, and pass without
the user's private dataset directory. A local real-data test is a separate
explicit invocation; it must not silently skip and count as acceptance.

## Real local DEM acceptance run

The implementation must provide one reproducible verification command or script
with a trusted local profile and an output directory. Document its actual
invocation after implementing it; do not give a nonexistent future CLI as a
command that already works.

The explicit run must:

1. Inspect inputs under `~/nasa/project/dataset`; select a verified small ROI and
   record why the DEM, units and transforms are suitable.
2. Save an input inventory with filenames, source metadata, dataset IDs/hashes,
   CRS, dimensions, mask/NoData, source resolution and chosen planning window.
3. Select and record nonidentical endpoints on valid cells. Save the exact
   `PlanRouteRequest` JSON; do not assume old mock fixture endpoints are covered.
4. Exercise both modes on the actual raster through the API, verify all emitted
   segments/cells, retrieve persisted metadata and repeat retrieval with a fresh
   app instance. A CLI-only path does not satisfy the API acceptance item.
5. Exercise an invalid endpoint/coverage case and a no-path or blocked-mask case
   with clearly labeled injected conditions where the natural ROI lacks one.
6. Emit a machine-readable verification summary and an English report under
   ignored `data/processed/a0-verification/<run-id>/`. Include exact commands,
   environment versions, profile/request paths, route IDs, response and artifact
   references, policy, timings, source hashes and each check's outcome.

Example HTTP requests once the implementation exists, the server is configured
for computed routing, and a real request JSON has been generated:

```bash
# Run from the directory containing the generated request.json.
curl --fail-with-body -sS \
  -H 'Content-Type: application/json' \
  --data-binary @request.json \
  http://127.0.0.1:8000/api/v1/routes/plan

# Replace ROUTE_ID with the returned opaque identifier.
curl --fail-with-body -sS \
  http://127.0.0.1:8000/api/v1/routes/ROUTE_ID
```

Do not download new archives or call a model as part of this run. If A3/A4/A6
downloads are present, verify their receipts and report their actual readiness;
if absent or rejected, retain the reason and continue terrain acceptance.
The existing RAD sample has a documented quality exclusion and must not become
a valid dose baseline simply because it was downloaded.

## Implemented local verification command

From the repository root, with the required packages installed:

```bash
cd backend
/home/sam/miniconda3/envs/nasa/bin/python -m app.planning.verify \
  --profile ../data/samples/a0-planning-profile.example.json \
  --dataset-dir "$HOME/nasa/project/dataset" \
  --output-root ../data/processed/a0-verification
```

Use your environment's `python` for a portable installation. The verifier
launches an actual localhost uvicorn process, calls both route objectives over
HTTP, validates and samples emitted segments, retrieves persisted records,
restarts the process and compares retrieval again. Labeled injected masks test
blocked endpoints and disconnection through TestClient; natural DEM results
remain separate. It inventories raster headers and optional source receipts
without downloading anything. Invalid optional inputs are recorded without
preventing terrain-only routing. It needs local socket permission; sandboxed
socket failures do not count as passing acceptance.

Each run creates a new `run-*` directory containing exact request/response and
retrieval JSON, input/grid inventories, source hash, copied profile, server log,
route artifacts, machine summary and English report. The final recorded run is
`run-20261114T063100Z-e4f307a3`. Its exact shortest request is:

```json
{
  "region_id": "jezero",
  "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  "start": { "longitude": 77.43516099910902, "latitude": 18.4599845417983 },
  "goal": { "longitude": 77.46361928030522, "latitude": 18.432991574025316 },
  "mode": "shortest"
}
```

Change only `mode` to `safest` for the other recorded objective. These endpoints
are valid CTX cells selected by the verifier, not unverified browser map picks.
For a separately started server configured as in [setup](setup.md), run:

```bash
curl --fail-with-body -sS -H 'Content-Type: application/json' \
  --data-binary @../data/processed/a0-verification/run-20261114T063100Z-e4f307a3/request-shortest.json \
  http://127.0.0.1:8000/api/v1/routes/plan
```

The HTTP server must use that run's `routes/` as `A_STELLAR_ROUTE_STORE` to
retrieve its existing recorded IDs, or use the newly returned ID when planning
against another store. The verifier stops its temporary server after checking.

## Frontend acceptance

- Verify the remote frontend reconciliation and preserved local work described
  in the [integration handoff](a0-frontend-integration.md). Record the actual
  revisions tested and any changes that remain unmerged.

- Add tests for computed result/retrieval decoding, metadata consistency,
  response ID matching, API errors and stale-request handling.
- Verify source-specific labels, null metric display and metadata fetching.
  A computed research result must not retain the hard-coded MOCK badge.
- Verify the map/wire/DEM adapter using documented source/control fixtures.
  Preserve the plotting guard when alignment is unverified; no hard-coded
  `true` toggle or mock-only coordinate bypass qualifies as validation.
- With a verified adapter, start frontend/backend, select the recorded local
  endpoints and check the computed polyline and metadata in the browser. Save
  evidence or report that browser verification was unavailable.
- Run `npm test` and `npm run build`. These do not by themselves demonstrate
  browser rendering or geographic alignment.

If external basemap access is unavailable, distinguish local API/geometry
checks from the browser/NASA imagery acceptance item. Do not report a complete
end-to-end map test from unit tests or a backend-only request.

## Optional LangGraph regression

When the optional dependencies are installed, preserve the existing scripted
regression. From `backend/`:

```bash
.venv/bin/python -m app.coordinator.cli \
  --request ../data/samples/a0-mission.json \
  --profile ../data/samples/a0-profile.json \
  --provider scripted \
  --script ../data/samples/a0-script.json
```

Its existing expected result is blocked route planning, seven tool calls, four
decisions, two replans, zero live model calls and a documented 160 +/-30 microSv
scenario. Inspect the generated report instead of assuming success from exit
code alone. This is a separate legacy evidence-loop regression, not the new
real A* acceptance test. Do not rewrite it to claim a computed route unless
that optional integration is deliberately implemented and documented later.

## Final report requirements

State what was implemented and what was actually run. Separate synthetic
correctness, actual DEM routing, persistent API retrieval, coordinate evidence,
browser display and optional graph regression. Include commands and result
paths; report failures, skipped/unavailable checks and remaining blockers.
Identify the tested frontend baseline and any remote/local integration gaps.
Do not reuse historical test counts as current results. An honest partial
report is necessary if an acceptance gate remains unresolved; it does not mark
the overall requested outcome complete.
