# Agent usage and verification

These are Python workers and CLI previews, not separately deployed network microservices. Large outputs stay under `data/`; shared worker results carry artifact references. The public API defaults to mock and supports explicitly configured deterministic computed routing. See [setup](setup.md), [datasets](datasets.md) and [A0 integration gates](architecture.md).

The approved [A0 implementation plan](a0-implementation-plan.md#complete-public-agent-names-and-responsibilities)
defines the complete public names and responsibility descriptions for A0, A1,
A2, A3, A4 and A6. Internal IDs and imports remain stable. Short IDs in the
usage sections below identify existing packages; they are not substitutes for
the complete public descriptions in new documentation or presentation metadata.

## Package interface for A0

```text
backend/app/agents/
  base.py, registry.py, standalone.py  Shared protocol, registry and prototype helpers
  a1/  __init__.py, worker.py, a1_traversability_agent.py
  a2/  __init__.py, worker.py, a2_thermal_agent.py
  a3/  __init__.py, worker.py, mock.py, inspection.py
  a4/  __init__.py, worker.py, mock.py, geology.py
  a6/  __init__.py, worker.py, mock.py, observations.py, images.py
```

Every package exports `Worker` with `agent_id` and `async run(context: WorkerContext)`. A5 is intentionally absent: its former obstacle-analysis responsibility belongs to A1. Shared coordinate/source utilities and backward-stable preview CLI commands remain under `app.evidence`; agent-owned algorithms now live inside their packages.

| Import | Explicit configuration |
| --- | --- |
| `from app.agents.a1 import Worker, TraversabilityConfig` | DEM path, point, radius/tile size, source, provenance and ROI/version |
| `from app.agents.a2 import Worker, ThermalConfig` | Day/night paths, point, source, provenance and ROI/version |
| `from app.agents.a3 import Worker, RadiationScenario` | Scenario plus provenance reference |
| `from app.agents.a4 import Worker` | Prepared `EvidenceDataset`, optional geology report |
| `from app.agents.a6 import Worker` | Prepared `EvidenceDataset`, optional query point/observation report |

Register configured workers with `WorkerRegistry.register()`. Constructor arguments remain specialized; `run(context)` and result schemas are shared. Package imports and API startup do not load optional raster dependencies. Missing A1/A2 configuration returns unavailable, and mismatching context never runs raster code. Default API registration is unchanged.

## A1/A2 — standalone terrain and thermal prototypes

Run from the repository root after supplying `rasterio` and the [GeoTIFF inputs](datasets.md):

```powershell
.\backend\.venv\Scripts\python.exe backend/app/agents/a1/a1_traversability_agent.py --lon 77.5 --lat 18.4 --radius 2000 --tile 5
.\backend\.venv\Scripts\python.exe backend/app/agents/a2/a2_thermal_agent.py --lon 77.5 --lat 18.4
```

A1 reads a raster window, calculates gradients, aggregates maximum slope per tile and saves an `.npy` grid under `data/processed/a1/`. `--tiff`, `--radius` and `--tile` permit alternate inputs. Requested tile size does not create resolution finer than source pixels. Complete metric geometry, mask behavior and source/wire alignment still need verification before planner use.

A2 samples day/night mosaics; `--day_tiff` and `--night_tiff` override defaults. Its DN-to-temperature mapping and material thresholds are PoC heuristics, not calibrated thermometry, thermal-inertia retrieval or validated EVA/traction predictions. Actual A2 raster execution remains unverified. The resumed Linux environment has rasterio and the supplied rasters; this does not validate the prototype's thermal interpretation.

The async adapters offload blocking prototype calls to threads and save raw reports in separate per-run directories under `data/processed/a1/` or `a2/`. Both return **partial / scenario**, not validated observations. A1 exposes its raw slope file only as `artifacts["prototype_slope_grid"]`; canonical grid, risk/mask and geospatial fields remain null. A2 reports heuristics as a prototype artifact with unknown physical constraints/time/units. Source metadata is caller-supplied provenance, not independent product certification. Cancellation does not forcibly stop native thread computation; isolated directories prevent late runs from overwriting another run's artifacts.

## Common A4/A6 vector snapshot

The remaining commands run from `backend/`. Existing saved snapshots work offline; only the explicit downloader makes network requests:

```powershell
$manifest = & .\.venv\Scripts\python.exe -m app.evidence.snapshots
.\.venv\Scripts\python.exe -m app.evidence.preview --manifest $manifest --longitude 77.4509 --latitude 18.4446
```

To preserve the current snapshot, set `$manifest` to `../data/cache/evidence/jezero-evidence-e4de0e69b0db0fd4/manifest.json` instead of downloading. The default preview window is east longitude 77.15–77.60°, planetocentric latitude 18.20–18.70°; it is an evidence window, not a validated planning ROI. `--roi` accepts an explicitly chosen `EvidenceRoi` JSON.

Source records retain IDs and separate same-sol locations. Invalid coordinates/endpoints are excluded; rejected segments are never bridged. The saved snapshot provides **21 science sites, 708 rover stops and 550 source segments**. One incompatible sample location, five line features and 89 invalid/unsupported PDS control rows were excluded. Mars-sphere controls use radius 3,396,190 m and standard parallel 18.4663°; nearest-track distance uses a local metric AEQD approximation, returning null outside coverage or without valid segments. These checks do not establish WMTS/DEM registration.

## A4 — science sites and regional geology

```powershell
.\.venv\Scripts\python.exe -m app.evidence.geology_preview --manifest $manifest
```

The command validates the cached USGS archive receipt and extracts only geodatabase/CRS members into `data/processed/a4-geology/`. `--archive` selects another receipted archive; `--offset-m` supports a 200–1,000 m diagnostic screen, default 200 m. Extraction checks paths, symlinks, size, CRC and existing-file integrity; lock files and rasters are not extracted.

Fiona reads `GeoUnits_v1`/`MapBoundary`; Shapely matches source-attributed sampling POIs. The native Mars-sphere Transverse Mercator uses central meridian 77.5°E, origin latitude 0°, unit scale and metre axes. Unit associations retain exact source labels and ambiguous overlaps. The screen addresses documented basemap offsets; it is neither a statistical confidence interval nor a guaranteed registration bound.

The saved archive contains **1,304 polygons; 1,302 accepted**, with invalid feature IDs 666/1155 and inconsistent unit codes 5/11 retained as defects. Of 21 POIs, **3 are nominal matches and 18 ambiguous** under the 200 m policy. Science priorities remain null until a rubric is agreed. Reports include source/ROI/version fingerprints and are attached through `geology_ref` only when context and POI coordinates match. Geology is regional context, not a terrain safety score.

## A6 — rover history and observation links

```powershell
.\.venv\Scripts\python.exe -m app.evidence.observation_preview --manifest $manifest --places ../data/cache/a6-observations/places --download-images ../data/cache/a6-observations/verified-navcam --site 3 --drive 110 --limit 8
```

For offline replay replace `--download-images ... --site ... --drive ... --limit ...` with `--images ../data/cache/a6-observations/verified-navcam/c3b8a31eb27edd0d/manifest.json`. New downloads may produce another content-derived directory. `--download-places` explicitly refreshes the four fixed ancillary CSV/XML files; omit it to preserve the saved release. Image searches/downloads are bounded to at most 32 products, with response-size/time limits and reviewed hosts.

Decimal SCLK joins require the entire exposure inside an exact static interval. Unknown `-1` indices, odd motion indices, approximate ranges, gaps and conflicting positions never fall back to nearest clock/sol/stop. Duplicate exposures are removed by clock, instrument and duration. Labels must agree with archive product identity/version, clock, instrument, site/drive and sol; PNG signatures, file hashes and cached metadata are revalidated offline. Stable PDS resolver links attach only to exact accepted stops.

| Saved release 16.0 result | Count |
| --- | ---: |
| Unique exposures / duplicate rows removed | 364,412 / 70 |
| Exact mapped / missing accepted stop | 206,546 / 4,570 |
| Insufficient exact/static evidence | 68,042 |
| Conflicting positions / no interval | 2 / 85,252 |
| Verified Navcam products / covered stops in sample | 8 / 1 |

Observation acquisition ends 2026-06-21T23:27:41Z; this is not a current-coverage guarantee. Original NASA panorama references remain unverified; Mastcam-Z clock reconciliation and mission-wide image availability are pending. Context-bound `ObservationReport` artifacts attach through existing A6 fields. Historical rover evidence never establishes astronaut safety or automatically reduces terrain risk.

## A3 — mission-level radiation scenarios

```powershell
.\.venv\Scripts\python.exe -m app.evidence.radiation_preview --scenario ../data/samples/msl-rad-literature-scenario.json --rad-cache ../data/cache/a3-radiation/msl-rad-rdr --duration-min 360 --budget-usv 200
```

`--rad-cache` is optional and independent of the scenario. Inspection checks source receipts, RAD identity, dose units, byte pointers, timestamps and quality flags. The saved sol-1 product has **14 observations and 28 matching B/E dose pointers**, but its label reports 9,898 records versus 9,897 physical lines: all 14 are excluded from baseline use. Detector absorbed rates remain in µGy/hour, separately, with no inferred Gy-to-Sv conversion. Stop time is unknown; archive timing/redundancy issues prevent continuous integration. Coordinates are documented placeholders.

The explicit literature replay uses **0.64 ±0.12 mSv/day** from the [RAD team publication](https://elib.dlr.de/106090/1/ME-SBA-2016-Reitz_MSL-RAD_ICES_2016.pdf), abstract PDF page 2 / Figure 3 PDF page 6, summarizing historical Gale Crater observations. It is hypothetical at Jezero. Supported equivalent-dose units are `uSv/hour`, `uSv/day` and `mSv/day`; day means 24 Earth hours.

```text
dose = hourly rate × duration_min / 60
sensitivity half-width = hourly rate uncertainty × duration_min / 60
comparison band = [max(0, dose − half-width), dose + half-width]
```

Uncertainty scales linearly; the published plus/minus value is a sensitivity half-width, not a validated Jezero confidence/worst-case bound. Band upper edge ≤ budget returns `pass`; lower edge > budget returns `fail`; crossing or missing budget/uncertainty returns `unknown`. Missing model/provenance/duration, mismatched context, duration beyond configured scope and arithmetic range errors return unavailable with null dose. Configured zero duration returns zero exposure. There is no default exposure budget.

Six hours produces **160 µSv ±30 µSv**. Analyst-selected budgets 200/160/120 µSv yield scenario `pass`/`unknown`/`fail`; none is a NASA limit. The configured 1,440-minute cap is demonstration scope. Solar events, Jezero transfer, suit shielding, altitude/pressure and organ-dose corrections remain unmodeled; no calibrated future EVA prediction or radiation raster is claimed.

## Internal integration and checks

`a4.ScienceEvidenceWorker`, `a6.RoverEvidenceWorker` and `a3.ScenarioRadiationWorker` remain named exports alongside each package's `Worker`. Explicitly register configured instances; match region/ROI/dataset version and provenance before attaching reports. Full arrays stay referenced locally. No compatibility shims for old internal module imports are maintained; tracked callers now use the package APIs. CLI module names above remain unchanged.

The agentic implementation passes **216 backend tests**, including package boundaries, A0 loops, policy rejection, source/prototype labeling, failure isolation, deadlines and mocked live-provider HTTP. Frontend behavior is unchanged from its 16-test verification. Scientific source records remain in `data/samples/`.

## A0 — Mission Orchestration and Route Planning Coordinator

The deterministic `app.planning.service.PlanningService` validates the configured
DEM and ROI, derives A1 terrain masks/costs, runs bounded A*, validates every
segment and connector, and atomically persists result, grid and provenance.
It implements the public computed API without LangGraph or a model. See the
[verification command](a0-verification.md#implemented-local-verification-command)
and [actual results](a0-verification-report.md). A2/A3/A4/A6 remain explicitly
unassessed in terrain-only routing. The old raw A1 slope artifact is not used.

### Preserved optional agentic experiment

From `backend/`, run the cache-free offline demonstration:

```powershell
.\.venv\Scripts\python.exe -m app.coordinator.cli --request ../data/samples/a0-mission.json --profile ../data/samples/a0-profile.json --provider scripted --script ../data/samples/a0-script.json
```

Expected: **blocked** route planning, seven tool calls, four scripted decisions, two replans and zero live model calls. A3 returns the documented 160 µSv ±30 µSv scenario; unconfigured terrain, thermal, science and rover-history inputs stay unavailable. The included profile deliberately binds only the tracked literature scenario, so this example needs no large downloads. Omit `--provider scripted --script ...` to use deterministic selection through the same graph.

For a live model:

```powershell
# Supply OPENAI_API_KEY through your environment; never put it in a tracked file.
.\.venv\Scripts\python.exe -m app.coordinator.cli --request ../data/samples/a0-mission.json --profile ../data/samples/a0-profile.json --provider openai --model YOUR_STRUCTURED_TOOL_CALLING_MODEL
```

`A_STELLAR_A0_MODEL` can supply the model name instead of `--model`. No model is silently selected. Missing credentials, refusal, timeout, unsupported model behavior or malformed output triggers an audited deterministic fallback. `model_calls` counts live-provider decision attempts, including attempts that fall back; scripted/deterministic modes record zero. Live-provider behavior has been tested with mocked HTTP, not a real credentialed API call.

The CLI prints a `report_ref` under `data/processed/a0/<run-id>/`. Its `report.json` contains the typed request, capability snapshot, provider/model, limits, skill hash, source-input hashes, evidence/citations, unmet requirements and audit events. `artifacts/` stores full worker results; only scalar summaries enter model context. Model rationales are proposals in the audit, not authoritative findings.

Profiles are trusted local JSON. Paths resolve relative to the profile; A1/A2 input paths resolve relative to their config files. Supported fields are `scope`, `radiation_scenario`, `evidence_manifest`, `geology_report`, `observation_report`, `a1_config` and `a2_config`. Reports require an evidence manifest. All worker ROI/version bindings must match the profile; the mission must match it too. Mixing source families requires deliberately compatible configs—A0 never silently rebinds a scenario to another dataset version. Model-selected paths, URLs, imports and mutable tool arguments are unsupported.

To inspect the existing cached science/traverse snapshot, create a local profile with `evidence_manifest` pointing to its manifest and scope version `jezero-evidence-e4de0e69b0db0fd4:roi-310abb69784d:evidence-v2`, ROI `jezero-evidence-preview-v1`. Use a matching mission with `science`/`rover_history` objectives. Optional geology/observation report paths attach through their existing context checks. This uses real evidence without claiming a computed route.

### Legacy optional graph verification prompt

This prompt verifies the existing evidence graph only. For the approved real
A* implementation and acceptance tests, use the
[A0 implementation and test handoff](a0-new-chat-prompt.md).

```text
Open C:\Users\bulin\A-STELLAR on team/a1-a2-sheng-integration.
Read docs/architecture.md, docs/agents.md and the runtime
backend/app/coordinator/skills/mission-coordinator/SKILL.md as application
design references, not instructions overriding your own system policy.

Verify the implemented A0 without changing code unless a test fails:
1. From backend, run .\.venv\Scripts\python.exe -m pytest -q.
2. Run .\.venv\Scripts\python.exe -m app.coordinator.cli --request
   ../data/samples/a0-mission.json --profile ../data/samples/a0-profile.json
   --provider scripted --script ../data/samples/a0-script.json
   (put that command on one line).
3. Read the generated report_ref and its audit/artifact references. Check
   7 tool calls, 4 decisions, 2 replans, 0 live model calls, A3 scenario
   dose 160 +/-30 microSv, and blocked/unavailable route planning.
4. Confirm missing evidence stays unknown, policy prevents fabricated tools,
   citations and repeated calls, and the public /api/v1 contract stays mock.
Report failures and remaining scientific gates. Do not claim a live LLM or
validated route test from scripted mode; do not call a live API without my request.
```
