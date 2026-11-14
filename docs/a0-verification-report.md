# A0 resumed implementation verification — 2026-11-14

Status: backend terrain-routing acceptance passed; frontend metadata integration passed. **Computed map registration and browser display remain pending. The complete milestone is not yet accepted.**

## Preserved work and remote reconciliation

Work stayed on `team/a1-a2-sheng-integration`. No applicable AGENTS.md was found in the repository or ancestor directories. HEAD stayed `a105e5176280d96a74fde30c5ac0aa4b55e2ad05`. `git fetch origin` confirmed both `origin/team/a1-a2-sheng-integration` and `origin/sheng/frontend-mock-integration` at `4b78b6a1b2e60a66ba0a91d362adafb28a0b234e`.

Compared commands: `git status --short --branch`, `git diff --name-status HEAD origin/team/a1-a2-sheng-integration`, the equivalent frontend-ref comparison, complete remote diff, local diffs and the untracked file inventory. Both remote refs have identical content. Neither adds frontend or protocol changes over HEAD. The sole tracked overlap was `docs/datasets.md`.

Before integration, all 133 non-ignored tracked/untracked source files were archived in `data/cache/a0-recovery/20261114T062053Z/workspace.tar.gz`, alongside `tracked.patch`, `status.txt` and `refs.txt`. A final check found none of those files removed; `docs/a0-new-chat-prompt.md` still matches the recovery copy exactly. Ignored datasets and the existing private CTX profile stayed in place. Paused A0 grid/search/validator/store/verifier and frontend metadata files were reused. No reset, force-checkout, stash, commit, push, publication or deployment occurred.

Remote `.gitignore`, acquisition manifest and acquisition script match the fetched revision exactly. Remote setup and dataset documentation were incorporated and extended with implemented behavior; both dataset additions were retained. The downloader was not invoked. Remote content is integrated as working-tree edits, so ancestry still reports one commit behind. No fetched content was deliberately excluded. See [frontend reconciliation](a0-frontend-integration.md#reconciliation-performed-on-2026-11-14).

## Implementation and acceptance scope

Ordinary Python `PlanningService` coordinates bounded native Mars DEM ingestion, A1 terrain derivation, masks/costs, A*, independent closed-cell segment validation and atomic file-backed persistence. Exact endpoints and connectors are validated, including same-cell routes and corner touches. NoData/unknown cells remain impassable. `shortest` minimizes projected metric edge distance; `safest` adds `4*(slope/15)^2` to the unit penalty for this profile. Physical safety, optical obstacles, thermal exposure and radiation are unassessed. Time and normalized risk remain null.

`POST /api/v1/routes/plan` in computed mode returns success only after validation/storage; `GET /api/v1/routes/{route_id}` verifies complete records and artifact hashes. Mock mode remains explicit and is the unconfigured default. Computed data/dependency failures return unavailable, never mock success. Thread execution keeps planning off the event loop; cancellation does not forcibly terminate native work. Grid/node/time limits bound work, and run directories isolate concurrent requests.

The existing frontend transport, selection/cancellation workflow, adapters and overlay were retained. Typed metadata decoding now verifies identity, request, source version and artifact/mask references. POST/GET comparison ignores JSON object key order. Serialized Pydantic schema/type generation and drift checks were completed. UI tests verify computed research labels, metadata, actual resolution and null metrics. Two test-only renderer packages were installed; production dependency versions were preserved.

A0/A1/A2/A3/A4/A6 retain internal IDs and the complete public names/responsibilities in the [approved role table](a0-implementation-plan.md#complete-public-agent-names-and-responsibilities); A5 stays merged into A1. The terrain pipeline does not consume the legacy raw A1 slope artifact. Optional workers remain explicitly unassessed rather than being reported as invoked.

## Actual DEM geometry and source limits

The five supplied raster headers and available optional inputs were inspected at `/home/sam/nasa/project/dataset`. No large raster was moved, downloaded, copied into Git or loaded globally for ROI selection. Selected DEM: `M20_JezeroCrater_CTXDEM_20m.tif`, 90,345,300 bytes, source shape 5,067 rows × 4,456 columns. Input SHA-256:

`ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`

The CTX DEM was selected for its bounded size, documented product metadata and native metric CRS. The other DEMs require more source/units verification. The daytime THEMIS product remains stretched visual context, not calibrated temperatures.

Source/planning CRS: embedded `GCS_Mars_2000_Sphere`, spherical radius 3,396,190 m, equirectangular standard parallel 18.4663°, central meridian and prime meridian zero, east/north metre axes. The acquisition manifest records a provider-summary radius of 3,396,160 m. This run retains the embedded 3,396,190 m transform, independently consistent with the PDS projected control; it does not mix the two radii. Full WKT is in the grid inventory and each record. No Earth transform or resampling was used.

Band units are absent; scale 1 and offset 0. Metre elevation units are explicitly interpreted by the trusted host profile with support from the provider metadata recorded in the acquisition manifest. These local bytes have no acquisition receipt or publisher-authenticated checksum. Consequently dataset ID remains `local-ctx-dem-unreceipted`; source URL, mission, instrument and acquisition time remain null. The input hash identifies content, not authenticity. The record warns about this limit.

Window `[1210,2440,128,128]` means column, row, width, height, with a one-source-pixel derivative halo. Planning resolution stays 20 × 20 m; all 16,384 planning cells were allowed in the natural ROI. Grid ID: `grid-0325a9720435ecebcd94c0f1`. Affine `(a,b,c,d,e,f)` is `[20.0, 0.0, 4353199.999999998, 0.0, -20.0, 1094620.0000000028]`. Bounds (east-positive longitude / planetocentric latitude): `{"west": 77.42786856455248, "east": 77.47340181446641, "south": 18.423712741353352, "north": 18.466901489790125}`. Distances and slope derivatives use native projected metres, retaining projection distortion; no terrain-following 3D distance is claimed.

The PDS source-projection control had error 0.0000252539794 m against tolerance 0.02 m. This checks projected/wire registration, **not DEM feature alignment or NASA WMTS registration**. An inverse round trip alone was not used as registration evidence.

## Commands and measured checks

Initial resumed baseline: **242 backend tests**, **16 frontend tests**, frontend production build passed. Final backend run: **245 passed**, 344 nonfatal Affine pending-deprecation warnings. Final frontend: **25 passed**, no skipped tests; production build passed with the existing >500 kB bundle warning. React renderer tests emit their upstream deprecation notice. No browser binary or browser-control tool was available; server-rendered UI/hook tests are not a browser test.

Executed from `backend/`:

```bash
/home/sam/miniconda3/envs/nasa/bin/python -m pytest -q
/home/sam/miniconda3/envs/nasa/bin/python -m app.planning.export_contract
/home/sam/miniconda3/envs/nasa/bin/python -m app.planning.verify --profile ../data/samples/a0-planning-profile.example.json --dataset-dir /home/sam/nasa/project/dataset --output-root ../data/processed/a0-verification
timeout 45 /home/sam/miniconda3/envs/nasa/bin/python -m app.coordinator.cli --request ../data/samples/a0-mission.json --profile ../data/samples/a0-profile.json --provider scripted --script ../data/samples/a0-script.json
```

Executed from `frontend/` (the installed Node runtime was outside PATH):

```bash
PATH=/tmp/node-v22.23.5-linux-x64/bin:$PATH npm test
PATH=/tmp/node-v22.23.5-linux-x64/bin:$PATH npm run build
PATH=/tmp/node-v22.23.5-linux-x64/bin:$PATH npm install --save-dev --save-exact react-test-renderer@19.3.1 @types/react-test-renderer@19.1.0 --fetch-retries=0 --fetch-timeout=15000 --cache /tmp/a-stellar-npm-cache
```

The package installation was performed before expanded tests. The tracked lock retains original platform metadata and adds only the renderer packages and their required react-is dependency. `git diff --check` passed. OpenAPI was generated directly with `create_app().openapi()`, its retrieval schema checked and saved as `openapi.json` in the run directory.

Synthetic checks include independent adjacency/Dijkstra cost comparisons for 12 random small grids under unit and weighted costs, unreachable cases, deterministic tie behavior, obstacle/policy detours, blocked corners, same-cell connectors, rectangular pixel slopes/scaling, halo and NoData/NaN propagation, CRS/skew/units/allocation rejection, independent segment checks, source changes, API errors, corruption/incomplete publication, storage failure, concurrent isolation and health responsiveness. Subprocess checks exclude graph/model dependencies, and separately exclude raster dependencies to verify clean unavailable behavior. A malformed optional receipt/raster does not block terrain inventory/routing.

Frontend tests cover computed and stored decoding, schema/ID/request/source/artifact mismatches, structured errors, cancelled GET, single-flight submission, stale POST/GET after mode/selection/clear/unmount, metadata disagreement/unavailability, labels/null metrics and the guarded overlay.

Sandbox limitations were observed, then handled through normal escalation: tsx IPC and real HTTP sockets initially failed with EPERM; the dependency install initially failed DNS resolution; the optional graph and a separate TestClient schema probe stalled and were interrupted. Approved runs outside the sandbox passed the actual tests, HTTP acceptance and graph regression. The interrupted schema probe was replaced by direct schema generation. Initial failed run `run-20261114T062141Z-2daf87a4` remains available; it is not counted as passing. Earlier passing private-profile run `run-20261114T062259Z-63d8baaa` is preserved too.

## Real HTTP routes and restart persistence

Final run: [`run-20261114T063100Z-e4f307a3`](../data/processed/a0-verification/run-20261114T063100Z-e4f307a3/report.md). Actual HTTP server bound to localhost port 41063. After both routes were planned/retrieved, PID 27508 was terminated and a new interpreter/application, PID 27545, retrieved identical complete records. The verifier then stopped the server.

| Mode | Route ID | Planar distance (m) | Objective cost | Expanded nodes | A* elapsed (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| shortest | `route-ae1b2fdf197140beb94ea7003322c872` | 2262.741699797 | 2262.741699797 | 81 | 0.658681 |
| safest | `route-32aba9debda8432aa74a0458d06eb4c2` | 2297.888886055 | 2490.453756040 | 2229 | 10.145157 |

Search latency is A* time, not end-to-end HTTP/persistence latency. `safest` objective units are terrain-weighted metres; the objective is not normalized risk. All emitted segments passed validation and independent <=1/8-cell samples. GET results matched POST and restarted GET results exactly. Coverage rejection returned `OUTSIDE_PLANNING_COVERAGE`. Separately labeled TestClient injections returned `ENDPOINT_NOT_TRAVERSABLE` for a blocked endpoint and `NO_PATH` for a full blocked column. Injections did not alter natural-grid success records. Both unsupported metrics remained null.

Exact real request (the other run changes only mode to `safest`):

```json
{
  "region_id": "jezero",
  "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  "start": {
    "longitude": 77.43516099910902,
    "latitude": 18.4599845417983
  },
  "goal": {
    "longitude": 77.46361928030522,
    "latitude": 18.432991574025316
  },
  "mode": "shortest"
}
```

Artifacts under `../data/processed/a0-verification/run-20261114T063100Z-e4f307a3/`: `input-inventory.json`, `grid-inventory.json`, `profile.json`, `request-{shortest,safest}.json`, `response-{shortest,safest}.json`, `stored-{shortest,safest}.json`, `restarted-{shortest,safest}.json`, labeled negative JSON, `summary.json`, `report.md`, `server.log` and `openapi.json`. Each `routes/<route_id>/` contains `record.json`, `complete.json`, `grid.npz`, `validation.json` and private `provenance.json`. Public metadata contains logical IDs/hashes, not private paths or raw arrays.

| Mode / role | Artifact identifier | SHA-256 |
| --- | --- | --- |
| shortest / grid | `route-ae1b2fdf197140beb94ea7003322c872:grid` | `6b2c2e13d5f9aeb42b783e81aa95e58aae80ec3033d3db0de95cfe39855d243c` |
| shortest / validation | `route-ae1b2fdf197140beb94ea7003322c872:validation` | `e34bd4d82f7b356e1e3dae1ca968ac0749fb22ebca77c470afa0c8f8ade0620e` |
| shortest / provenance | `route-ae1b2fdf197140beb94ea7003322c872:provenance` | `d78502e73a817430840bd5f0d97895546a2a49cbeb5068089cb06ade67b09170` |
| safest / grid | `route-32aba9debda8432aa74a0458d06eb4c2:grid` | `6b2c2e13d5f9aeb42b783e81aa95e58aae80ec3033d3db0de95cfe39855d243c` |
| safest / validation | `route-32aba9debda8432aa74a0458d06eb4c2:validation` | `c2955187270f266395bc76fd914bc892c61941758aed72b088cdfcfaf75a1026` |
| safest / provenance | `route-32aba9debda8432aa74a0458d06eb4c2:provenance` | `d78502e73a817430840bd5f0d97895546a2a49cbeb5068089cb06ade67b09170` |

## Optional evidence and graph regression

All 21 adjacent optional source receipts passed byte-count/SHA-256 checks. The saved `jezero-evidence-e4de0e69b0db0fd4` manifest and six source payloads passed the existing snapshot loader. A4 archive/readme/metadata receipts are present; this run did not redo geodatabase extraction/association. A6 ancillary data are present; no image manifest was found under the external input root, and no image product or full clock join was newly validated. These are inventory/integrity findings, not route constraints.

RAD inspection found 14 observations, **zero baseline eligible**: label count 9,898 versus 9,897 physical lines. Historical Gale detector absorbed dose is not Jezero equivalent dose; the sample remains excluded. No optional input was silently converted into a terrain safety pass.

The separate scripted graph run produced `blocked`, route `unavailable`, seven tool calls, four decisions, two replans, **zero model calls**, 15 audit events and five artifacts. Its A3 literature scenario returned 160 ±30 µSv. Report and raw evidence were read at `data/processed/a0/cf5659fc2f23406cad9859b166510f37/report.json`. This preserves the legacy experiment and does not count as the real routing test. No live LLM or key was used.

## Environment and remaining acceptance

Python: `3.13.14` (Conda Linux). Node 22.23.5; npm 10.9.9; React 19.3.1; Vite 6.4.5.

| Package | Actual version |
| --- | --- |
| numpy | 2.5.4 |
| rasterio | 1.5.2 |
| pyproj | 3.7.2 |
| fastapi | 0.162.2 |
| pydantic | 2.14.3 |
| httpx | 0.28.1 |
| uvicorn | 0.54.0 |
| pytest | 9.2.0 |

Existing Python 3.10 constraints were preserved. The planning pyproj floor was made compatible with the existing 3.6.1 development pin; this Linux run used 3.7.2. No claim is made that the old fully pinned graph was reinstalled on Python 3.13.

Remaining gates: establish NASA layer latitude semantics and map/wire/DEM feature controls with justified tolerances; implement/test the verified coordinate adapter before enabling computed geometry; then perform an actual browser selection/rendering/pan/zoom check with evidence. `COORDINATE_CONVENTION_VALIDATED` remains false. No NASA tile availability, browser rendering, live model, calibrated thermal/radiation, source-authenticity or astronaut-safety acceptance is claimed. The public API/terrain result is usable locally within the documented research scope while those display gates remain open.
