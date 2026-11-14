# A-STELLAR — Jezero Crater Backend Team Master Plan

**Status:** Implementation-ready team plan, v1.0 (2026-11-08)
**Mission area:** Jezero Crater, Mars — **one verified, small DEM-covered region of interest (ROI)** to start
**Development model:** One monorepo, two parallel workstreams, one stable frontend/backend protocol
**Owners:** **Sam: A1 + A2** | **Sheng: A3 + A4 + A6**
**Architecture:** **A0 LLM Mission Coordinator** + five deterministic/algorithmic specialists + Risk/Evidence Fusion + deterministic route planner.

> **Read first:** `docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md` is the authority for the **existing external API** (`/api/v1/...`, coordinate and error conventions). This master plan defines **internal modules, work division, and execution sequence**. If an example here disagrees with the existing protocol document, the existing protocol wins until both developers approve a versioned change.

---

## 1. Goal and scope

Deliver a working vertical slice with **real Jezero data**: user picks Start/Goal in the existing React/OpenLayers map → FastAPI receives a Mars coordinate request → surface model produces terrain-based passability/risk → deterministic route planner finds and validates a route → frontend displays route and evidence. Expand this to science goals, historical rover evidence, thermal context, and mission radiation budget without weakening provenance or safety checks.

**MVP success:** (1) one real, georeferenced Jezero ROI; (2) computed DEM-based traversability; (3) path planner; (4) coherent frontend route; (5) source/coverage metadata and honest caveats. A0 LLM, A2, A3, A4 and A6 enrich the MVP incrementally; a complete suite is the final target, not the day-one dependency.

**Safety boundary:** Research / hackathon decision-support prototype only; **not** flight-qualified astronaut navigation. Missing or coarse NASA measurements must be represented as unknown/unavailable, **never assumed zero risk**. Rover-traversed does **not** mean astronaut-safe.

## 2. Final agent list and ownership

| ID | Agent / worker | Owner | Data / inputs | Core computations | Output and UI layer | Priority |
|---|---|---|---|---|---|---|
| **A0** | Mission Coordinator (**LLM later**) | **Shared integration**; Sheng starts deterministic skeleton, Sam reviews | Mission intent, availability registry, start/goal/POIs, risk policy | Choose tools, manage steps, request planning, interpret failures, propose replans; **never generate/execute arbitrary Python** | Planning decisions, tool trace, explanations | P0 skeleton, P2 LLM |
| **A1** | Surface Traversability (**includes old A5 Visual Hazard**) | **Sam** | Jezero HiRISE DEM/orthomosaic, masks | Elevation, slope, roughness, optional visual obstacle candidates, hard-block mask, traversability cost | Elevation / slope / roughness / hazard / traversability overlays | **P0** |
| **A2** | Thermal Environment | **Sam** | THEMIS observations, MEDA when available, timestamps & units | Thermal context, temporal validity, scenario-based exposure only if calibrated inputs exist | Thermal context overlay or status panel, not fabricated local temperature | P1 |
| **A3** | Radiation Exposure | **Sheng** | Credible radiation dataset/model, EVA duration, policy limits | Estimate accumulated dose / budget under explicit assumptions; handle unavailable data | Mission-level radiation status and constraints; **not** a fake 1-m radiation map | P2 |
| **A4** | Science Opportunity | **Sheng** | Jezero geological map, mineral/spectral records, documented sampling POIs | Curate georeferenced POIs, rationale, deterministic priority scoring | Geology and science POI vector layers | **P1** |
| **A6** | Rover Traverse Intelligence | **Sheng** | Perseverance historical traverse/sol locations, accessible image metadata | Traverse overlay, nearest observed traverse, historical observation links; coverage/evidence only | Rover route, sol points, historical observation references | **P1** |

**Why no A5?** Old A5 optical obstacle analysis belongs inside **A1** because optical hazards + DEM hazards both contribute to the same surface traversability model. A1 may expose separate optical and topographic sublayers. A4 and A6 share the same observation catalog but have different responsibilities: **science value vs rover history/evidence**. A2 and A3 remain separate due to fundamentally different physics and temporal/spatial scales.

### Shared deterministic services — not additional LLM agents

- **Data Catalog and Geo Alignment:** dataset IDs, official download links, coverage, Mars CRS, resolution, timestamps, reprojection, NoData, cache. Implement initial common interface in shared B0; owners maintain their own ingestion adapters.
- **Risk & Evidence Fusion:** combine *compatible* spatial costs/masks; preserve provenance and unknown areas. Keep thermal/radiation route/time constraints separate when rasters are not defensible.
- **Route Planner:** A* / Dijkstra on a correctly projected **metric** grid, with hard-block cells and validated start/goal; report route + metrics + warnings.
- **Route Validator:** verify known constraints, dataset coverage, route validity; no LLM override.

**Integration ownership:** Sheng wires initial FastAPI A0 skeleton and route-facing interfaces; Sam owns implementation of A1 grid/cost output; **both jointly** test Fusion / Planner and frontend integration. Do not leave A0/Planner unassigned simply because their names are not in A1–A6 ownership.

## 3. One architecture, parallel work

```text
React + OpenLayers (existing frontend)
  |-- browser -> NASA/USGS imagery tiles (WMTS/WMS) [display only]
  `-- POST /api/v1/routes/plan -------------------------------.
                                                               v
                                                       FastAPI v1 boundary
                                                               |
                                                     A0 Mission Coordinator
                                                      (initially rules-based)
                                                               |
                                         +---------------------+--------------------+
                                         |                     |                    |
                                Sam workstream           Sheng workstream       Shared services
                                A1 Surface               A3 Radiation          Data Catalog
                                A2 Thermal               A4 Science            Risk/Evidence Fusion
                                                         A6 Rover               A* Planner/Validator
                                         |                     |                    |
                                         `---------------------+--------------------'
                                                               |
                                              Validated computed route + evidence
                                                               |
                                                   existing /api/v1 response
```

**Orchestration policy:** A0 may select *which registered* workers to invoke and with what **validated parameters**. Worker classes and their scientific methods are authored/tested by the team; A0 does not synthesize worker code. In the first milestone, orchestration is a deterministic Python dispatcher; introduce LLM structured output/tool calling only after it works without LLM.

## 4. Mandatory shared contract — agree before parallel coding

### 4.1 External frontend/backend contract (unchanged)

- `GET /api/v1/health`
- `GET /api/v1/regions`
- `POST /api/v1/routes/plan`
- Request fields and response envelope must follow **`docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md` exactly**, including `source: "mock" | "computed"`, nullable unknown metrics and standardized error envelope.
- **Wire coordinate convention:** `MARS_2000_PLANETOCENTRIC_EAST_360_V1`: east-positive longitudes **[0,360)**, **planetocentric** latitude **[-90,90]**, always named `longitude`/`latitude` fields. This is **an application contract, not an EPSG code**. Do not silently swap to east-180, planetographic, EPSG:4326 or Earth `fromLonLat()`.
- UI converts Mars map-view coordinates into wire coordinates using **one verified adapter**; backend converts wire coordinates to local projected DEM meters/grid positions using dataset-specific transforms. Preserve exact map alignment tests.
- Add new internal or optional presentation endpoints **only after** both sides agree on a documented schema; never break existing route POST.

### 4.2 Internal worker contract (all developers implement)

Use shared typed data definitions; **no raw geospatial arrays in JSON or LLM context**. Suggested Python/Pydantic model fields:

```python
class WorkerContext(BaseModel):
    mission_id: str
    region_id: Literal["jezero"]
    roi_id: str
    dataset_version: str
    # Optional, typed mission parameters are validated upstream.

class WorkerResult(BaseModel):
    agent_id: Literal["A1", "A2", "A3", "A4", "A6"]
    status: Literal["ready", "partial", "unavailable", "failed"]
    artifacts: dict[str, str]       # artifact IDs / local references
    dataset_ids: list[str]
    warnings: list[str]
    provenance_ref: str | None
```

This is a **common envelope**, not the only result schema. Add agent-specific typed result objects:

- **A1:** `grid_id`, `slope_ref`, `roughness_ref`, `risk_ref`, `hard_block_ref`, `coverage_ref`, `unknown_ref`, geospatial metadata.
- **A2:** observation unit/time/coverage, thermal raster **only if valid**, exposure/uncertainty/availability.
- **A3:** assumed dose rate or model reference, `dose_estimate` with units, duration, budget and limitations; potentially **no raster**.
- **A4:** typed `SciencePOI` (`id`, coordinates in wire convention, category, source, scientific rationale, priority method).
- **A6:** traverse polyline/sol points and observation references, data timestamp/coverage, proximity results; **no automatic safety promotion**.

**Every artifact** must record: original source URL and dataset ID, instrument/mission, acquisition time, download date, bounding region, Mars coordinate convention, projection, grid transform, resolution, NoData/coverage/unknown mask, resampling, processing version and uncertainties. A score `[0,1]` requires an explicit tested normalization model; no LLM-invented confidences.

### 4.3 Storage rules

- Never commit multi-GB DEM, image rasters, credentials or tokens to Git.
- Small synthetic fixtures belong in `data/fixtures/`, source manifests in `data/samples/`, and source documentation in `docs/datasets.md`.
- Intermediate georeferenced rasters can live in `data/cache/` / `data/processed/` (**gitignored**), with stable metadata/artifact IDs. Raster and vector previews may be served as map-compatible overlays later.
- No scientifically meaningful raster calculation from colorized WMTS/WMS tile pixels unless the tile actually carries calibrated physical values and that is verified. Fetch numeric DEMs / calibrated scientific products separately.

## 5. Implementation phases and explicit ownership

### B0 — Foundation and API integration (both; do **first**)

**Sheng**
1. Set up/verify FastAPI app, health/regions/routes contract and standardized errors, OpenAPI docs and tests.
2. Define `WorkerContext`, `WorkerResult` and specialized output schemas under `app/contracts/`; create an allowlisted registry for A1, A2, A3, A4, A6.
3. Create deterministic `MissionCoordinator` skeleton and `AgentDispatcher`, handling unavailable/failed/partial workers and timeouts. Keep preexisting mock route behavior for integration.
4. Add simple mock A3/A4/A6 outputs with **explicit mock status**.

**Sam**
1. Review/approve shared contract, implement mock A1 and A2 under the agreed worker interface.
2. Create small synthetic metric DEM fixture (e.g. 30x30) with blocked/unknown cells and tests for A1 planned output.
3. Write `docs/jezero-data-manifest.md` (or equivalent section in `docs/datasets.md`) listing verified accessible DEM/orthomosaic and thermal sources, expected coordinates, resolution and missing data.

**Together:** agree on one Jezero ROI and verify DEM coverage, coordinate axes/CRS, grid origin/resolution; record exact sample fixture points. Demo `POST /api/v1/routes/plan` still works unchanged.

**Exit:** Two independent worker mocks are callable via registry; route API contract tests pass; no unresolved convention mismatch.

### B1 — Data ingestion / independent specialist development (parallel)

**Sam — A1 Surface Traversability (P0)**
1. Obtain a real Jezero DEM and matching orthomosaic as *raw georeferenced science products* (USGS/PDS), **not the color-shaded MOLA global WMTS raster**.
2. Select a small DEM-covered ROI; inspect georeferencing, true metric scale, NoData/mosaic confidence. Persist metadata + canonical local grid.
3. Compute metric slope/roughness using valid-mask-aware neighboring operations; define an explicit task-configured slope threshold for hard block as **demo assumption**, not certified astronaut limit.
4. Convert to spatial traversability cost and obstacle/unknown masks; imagery-based candidates are optional until imagery georegistration and validation are demonstrated.
5. Unit tests: flat plane; uniform incline; NoData; edge behavior; high slope; mismatched CRS/resolution; stable result artifacts.

**Sam — A2 Thermal (P1, parallel after A1 foundation)**
1. Inventory Jezero thermal context sources: THEMIS and/or MEDA as appropriate; record instrument, units, observation date, local time, spatial footprint.
2. Define data adapter + thermal availability/coverage result first.
3. Only add numeric temperature/exposure interpretation when raw calibrated values and time conditions support it; otherwise return `partial` / `unavailable` with meaningful context.
4. Tests: unit conversions; unavailable data; observation time mismatch; no invented fine-resolution values.

**Sheng — A6 Rover Traverse (P1)**
1. Locate/export Perseverance traverse history and sol/observation reference data from official NASA/PDS sources; validate download, license and spatial convention.
2. Normalize route to canonical Mars wire convention; maintain dataset provenance and sol chronology.
3. Provide mapped route/stop points (GeoJSON if appropriately georeferenced), `nearest_track_distance_m` computed in proper local metric CRS, and references to accessible Navcam/Mastcam-Z images.
4. Tests: duplicate Sol handling; missing position; coordinate wraparound; nearest-track geometry; unknown coverage.

**Sheng — A4 Science Opportunity (P1)**
1. Load official Jezero geologic GIS units and documented Perseverance sampling/science POIs; keep source IDs and verified coordinates.
2. Normalize to the agreed ROI and canonical coordinate convention.
3. Provide POI filtering, categorization and a transparent deterministic scoring rubric (or return unranked POIs until a rubric is agreed).
4. Tests: POI out of bounds; duplicate sites; missing provenance; unit overlap; stable rankings with fixed criteria.

**Sheng — A3 Radiation Exposure (P2)**
1. Catalog legitimate ionizing radiation observations/models with limitations; **do not confuse MEDA solar radiation/dust measurements with astronaut ionizing dose**.
2. Implement a mission-level model: dose-rate assumption or validated model × EVA time, with explicit units, uncertainty, source and scenario.
3. Return constraints/status; if defensible data not available, return `unavailable`. No cell-wise Jezero radiation map without validated spatial model.
4. Tests: zero/positive duration; unit math; missing source; uncertainty; constraint threshold logic.

**Exit:** Workers independently return typed outputs, artifacts and provenance for one agreed ROI. Unavailable science is labeled explicitly, not silently substituted with fake measurements.

### B2 — Deterministic route planner & first real vertical slice (both; P0)

**Sam** supplies A1 local grid, cost/masks, dataset fixtures and meter-based coordinate transform tests.
**Sheng** implements/wires shared `RiskFusionService`, `AStarRoutePlanner` and `RouteValidator` (Sam reviews geometry/risk behavior).
**Together** verify start/goal → map CRS → DEM cells → computed path → back to wire Mars coordinates → OpenLayers overlay.

Required behavior:
- A* avoids blocked and unknown cells by default; use a documented explicit policy if unknown traversal is enabled in demo mode.
- `shortest` vs `safest` genuinely use different, defined cost weights when possible; no claim of safety guarantee.
- Detect unreachable start/goal and disconnected targets; return documented API error.
- Metrics `distance_m` and `risk_score` only when calculated from a named, tested model; `estimated_time_min` only with a declared walking-speed assumption.
- `source: "computed"` only when path is actually computed from the validated planning grid; route includes dataset/provenance metadata as **agreed additive field** if front end supports it.

**Exit:** an end-to-end computed, visible Jezero route; reproducible simple corridor/obstacle tests; screenshot/video plus test logs.

### B3 — Evidence-enhanced and science-aware routing (Sheng lead; Sam supports)

- A4 supplies **grounded** science POIs and optional priorities; A6 supplies historical rover traverse/observation evidence.
- A0 (still can be rules-based) chooses eligible POIs and proposes mission itinerary.
- Planner supports `start → POI(s) → goal` using validated segment routes, distance/time budgets and constraint checks.
- Optional rover-history proximity can be shown as a distinct **evidence layer**, not automatically lower routing cost. Only introduce a history-based cost adjustment if justified and evaluated separately.
- Keep current `/routes/plan` contract; new multi-stop API should be additive (proposal: `POST /api/v1/missions/plan`) with explicit schema approval.

**Exit:** route to documented science sites; rover tracks and observations shown independently; explanation references source datasets.

### B4 — Environmental constraints (Sam A2, Sheng A3)

- A2 exposes coarse/time-bound thermal context; A3 supplies radiation dose estimate/budget.
- Risk/Evidence Fusion consumes **typed** thermal and radiation constraints; never force both to 1-meter raster costs.
- Model estimated mission duration; validate time and exposure budgets. Return infeasible/unknown when appropriate.
- Optional scenario simulation: compare routes with/without thermal or radiation assumptions, **clearly labeled scenarios**.

**Exit:** route status distinguishes pass/fail/unknown constraints; uncertainty is visible to frontend.

### B5 — A0 as actual LLM Agent (Sheng initial implementation; Sam reviews safety/tools)

- Keep validated deterministic worker registry and planner as tools.
- LLM receives user mission goal and **only worker descriptions, typed capability metadata and safe outputs**, not huge rasters.
- LLM produces a schema-validated `MissionPlan` (selected tools, constraints, destinations). Validate all action names, ROI IDs and numeric parameters against server policy.
- Orchestrator executes selected workers, fuses valid outputs, calls planner and checks validator. LLM may propose alternatives on failure but may **not** waive safety limits or invent missing datasets.
- Cap tool calls/replan attempts; log tool traces and data versions; support deterministic no-LLM fallback.
- No need for 5 independent LLM calls; A1/A2/A3/A4/A6 remain algorithmic workers.

**Exit:** reproducible example of natural-language request → structured tools → validated route / explicit infeasibility; audit log.

### B6 — Validation, demo and release (both)

- Synthetic unit tests + real ROI smoke tests + frontend E2E.
- Failure tests: absent DEM, projection mismatch, out-of-ROI, NoData, no route, stale thermal records, unavailable radiation, contradictory POIs, rover track without route safety evidence, malformed LLM plan, missing backend.
- Document dataset provenance/credits and actual spatial/temporal limits. Record a 2–3 minute demo showing NASA layer + slope/route + science POI + historical traverse + optional thermal/radiation status.
- Report **measured** outcomes: route distance, percent of traversed cells with valid data, constraint result, latency, available POI count. Never claim flight qualification.

## 6. Repo structure (suggested; adapt to existing code, do not destructively reorganize)

```text
A-STELLAR/
  frontend/                           # existing React/OpenLayers
  backend/
    app/
      main.py
      api/                            # keep v1 endpoints stable
      contracts/                      # shared Pydantic input/output, grid, provenance
      coordinator/                    # A0 deterministic, later LLM
      agents/
        registry.py
        base.py
        surface_traversability.py     # A1 — Sam (includes optical A5)
        thermal.py                    # A2 — Sam
        radiation.py                  # A3 — Sheng
        science.py                    # A4 — Sheng
        rover_traverse.py             # A6 — Sheng
      services/
        data_catalog.py
        geospatial.py
        risk_fusion.py
        path_planner.py
        route_validator.py
      tests/
        test_contract.py
        test_agents_*.py
        test_planner.py
    pyproject.toml
  data/
    raw/                              # local DEM/thermal inputs; gitignored
    fixtures/                         # small coordinate/API golden fixtures
    samples/                          # tracked scenario/source records
    cache/                            # gitignored
    processed/                        # gitignored
  docs/
    README.md                         # documentation index
    datasets.md                       # sources, paths and provenance
    A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md
    A_STELLAR_JEZERO_TEAM_BACKEND_MASTER_PLAN.md
```

## 7. Parallel Git workflow and interface freeze

1. Create milestone `B0: Contracts + agent skeleton` and assign owner tickets below; merge B0 shared contracts **before** Sam/Sheng diverge on worker modules.
2. Work on feature branches (`feat/sam-a1-surface`, `feat/sam-a2-thermal`, `feat/sheng-a6-traverse`, `feat/sheng-a4-science`, `feat/sheng-a3-radiation`, `feat/shared-planner`, `feat/a0-coordinator`). Small PRs; other developer reviews.
3. Avoid conflicting changes to `app/contracts/` and `app/api/`: submit contract-change PR separately, attach fixture and migration reasoning, approve both owners first.
4. CI: `ruff`/lint (if configured), `pytest`, API contract tests. A PR with missing science data must still pass by emitting `unavailable` rather than generating fake data.
5. Keep explicit README commands for installing dependencies and running demo; lock versions once chosen.

### First issue set

| Issue | Owner | Dependency | Deliverable |
|---|---|---|---|
| B0-01 API/coordinate contract freeze and typed schemas | **Sheng + Sam review** | existing protocol | shared types + golden fixtures |
| B0-02 A0 deterministic dispatcher + registry | **Sheng** | B0-01 | runs mocks; handles failures |
| B0-03 A1 mock + synthetic DEM test harness | **Sam** | B0-01 | terrain typed result and tests |
| B0-04 A2 mock + thermal data inventory | **Sam** | B0-01 | thermal typed result + source inventory |
| B0-05 A3/A4/A6 mock + data inventory | **Sheng** | B0-01 | typed results + provenance |
| B1-01 Real Jezero DEM + A1 slope/cost | **Sam** | B0-03 | georeferenced risk raster/masks |
| B1-02 Rover traverse normalization | **Sheng** | B0-05 | historical track + Sol records |
| B1-03 Science POI/geology normalization | **Sheng** | B0-05 | verified science POIs |
| B2-01 Risk fusion + deterministic A* | **Sheng**; Sam review | B1-01 | computed route in one ROI |
| B2-02 Frontend integration acceptance | **Both** | B2-01 | visible API route overlay |
| B4-01 Calibrated thermal/status model | **Sam** | B0-04 | A2 typed output |
| B4-02 Radiation dose/status model | **Sheng** | B0-05 | A3 typed output |
| B5-01 LLM A0 tool selection | **Sheng**; Sam review | deterministic integration | validated mission plan + audit |

## 8. Definition of done and handoff checklist

An Agent PR is **done** only when:

- [ ] Imports and `run(context)` comply with shared schema; type/status variants are documented.
- [ ] Real inputs are distinguished from fixtures and scenarios; sources/timestamps are cited in metadata.
- [ ] Unit tests cover valid, missing, malformed and out-of-coverage inputs.
- [ ] Coordinate conventions and units are explicit; no Earth coordinate shortcuts.
- [ ] NoData/unavailable/unknown is **not** zero risk.
- [ ] Artifacts have stable references and provenance; large rasters are not committed.
- [ ] Errors are returned in a way A0/dispatcher can handle without lying about completion.
- [ ] At least one example call/fixture is included for integration.

Backend vertical-slice **done** when:

- [ ] F1.5 endpoint contract tests pass unmodified.
- [ ] A1 real DEM ROI and known coordinates align with map imagery.
- [ ] Real A* route computed, validated, converted to Mars API coordinates, and rendered in frontend.
- [ ] Distinguish `mock` versus `computed`; noncomputed metrics are `null`, not fabricated.
- [ ] A4/A6 optionally enrich output without being required for simple start/goal routing.
- [ ] Missing A2/A3 data is visible as unknown and does not masquerade as safe.
- [ ] Tests + documentation make results reproducible.

## 9. Codex handoff prompts (copy to separate workspaces/branches)

### Sam (A1 + A2)

> Read `docs/A_STELLAR_JEZERO_TEAM_BACKEND_MASTER_PLAN.md` and `docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md`. You own **A1 Surface Traversability** (including the former A5 Optical Hazard functionality) and **A2 Thermal Environment**. First inspect the existing repo; implement only B0-03/B0-04 using the shared typed worker interfaces and tests. Do not alter `/api/v1` externally or change Mars coordinate conventions. Then implement a verified Jezero DEM ingestion, metric slope/roughness, coverage/unknown mask and traversability raster in A1. Inventory thermal data before estimating temperature; if unsupported, return `partial`/`unavailable` with provenance. Avoid LLM frameworks. Keep PRs scoped and do not commit large datasets.

### Sheng (A3 + A4 + A6, A0 integration lead)

> Read `docs/A_STELLAR_JEZERO_TEAM_BACKEND_MASTER_PLAN.md` and `docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md`. You own **A3 Radiation Exposure**, **A4 Science Opportunity**, **A6 Rover Traverse Intelligence**, and initial **A0 coordinator/registry + shared planner integration**. First implement B0-01/B0-02/B0-05: shared typed schemas, deterministic dispatcher and honest mock outputs with tests. Preserve the wire API and `MARS_2000_PLANETOCENTRIC_EAST_360_V1` convention. Next build source-grounded Perseverance track and Jezero POI adapters; build A* using the canonical cost-grid output supplied by Sam. Radiation is mission-level, never a fabricated per-pixel map. Add LLM A0 only after the deterministic path is end-to-end validated. Keep PRs scoped and coordinate any shared contract changes.

### Joint integration

> Read both protocol and master plan. Verify a known Jezero coordinate fixture between OpenLayers, Mars wire API and the DEM grid. Connect Sam's A1 risk output to the shared deterministic planner, preserve existing FastAPI response schema, and display the computed route in React. Test unknown cells, invalid coordinate systems, unavailable specialists and an unreachable goal. Do not call the route astronaut-safe or NASA-certified.

## 10. Key references / data entry points

These are **starting points for verification**, not guarantees that every desired product is directly downloadable in the correct format:

- NASA Mars Trek map / tiled layer documentation: https://trek.nasa.gov/mars/ and https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
- USGS Jezero terrain-relative-navigation HiRISE mosaics/DEM: https://www.usgs.gov/data/mars-sample-return-hirise-mosaics-terrain-relative-navigation
- USGS Jezero / Nili Planum geologic map: https://pubs.usgs.gov/publication/sim3464
- NASA Perseverance location map: https://science.nasa.gov/mission/mars-2020-perseverance/location-map/
- PDS Analyst's Notebook: https://an.rsl.wustl.edu/
- Perseverance MEDA data archive entry: https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html

**Next action:** Merge B0 shared schemas first. Sam and Sheng then proceed independently on their assigned agents while keeping one frozen API/coordinate protocol. Prioritize **A1 + deterministic planner** to obtain a computed Jezero route before integrating all other modules.
