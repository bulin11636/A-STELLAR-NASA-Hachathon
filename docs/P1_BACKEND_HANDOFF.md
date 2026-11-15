# P1 backend policy and assessment handoff

This implements Sam's backend scope in [the ownership plan](P1_TOKEN_WEIGHTED_OWNERSHIP_PLAN.md).
Work is based on `main` at `a2be88b`. Product layout, profile/resolution selectors,
Journey Briefing and the verified-map presentation remain Sheng's work.

## Stable frontend entry points

- `GET /api/v1/planning/policies`: typed, versioned profile and resolution catalog.
- `POST /api/v1/routes/plan`: optional `mission_profile` and `resolution_profile`.
- `GET /api/v1/routes/{route_id}`: immutable `assessment`, `planning_policy`,
  `legs`, `registration`, specialist traces and source metadata.
- `GET /api/v1/planning/registration`: local diagnostic. Without an actual route
  footprint it cannot grant route-specific map registration.

Generated types live in `frontend/src/types/routeMetadata.ts`. Runtime schemas
include `policies.schema.json`, `storedRoute.schema.json` and `chat.schema.json`.
`getPlanningPolicies()` provides a strict browser client. Shared planner state
exposes profile/resolution values and preserves them in frozen requests, retry,
metadata retrieval and reload. No profile or resolution UI control is added here.

Use the advertised `mode` with the selected profile. For example, extend a valid
Jezero request with:

```json
{
  "mode": "safest",
  "mission_profile": "balanced",
  "resolution_profile": "fine",
  "mission": {
    "mode": "walking",
    "speed_m_s": 1.0,
    "stop_minutes_per_waypoint": 3.0,
    "exposure_duration_min": null,
    "radiation_budget_usv": null,
    "required_analyses": []
  }
}
```

Speed is an example input, not a default or a Mars EVA recommendation. A profile
with a conflicting objective receives `PROFILE_OBJECTIVE_MISMATCH` before any
model request. Arbitrary weights and unknown fields are rejected. Legacy requests
may omit profile/resolution; their existing `shortest`/`safest` cost is retained,
and the applied metadata explicitly identifies the legacy objective path.

## Approved policies

Policy version: `jezero-walking-policy-v2`. Each profile has its own immutable
`<profile_id>-v2` version. Profile dictionaries are fresh copies; mutating a
caller-owned copy cannot change future server policy.

| Profile | Advertised mode | Host terrain-weight multiplier | Special boundary |
| --- | --- | ---: | --- |
| Safest | `safest` | 1.5 | Relative engineering preference, never a safety certificate |
| Fastest | `shortest` | 0 | Shortest projected traverse under a constant supplied speed |
| Science priority | `safest` | 0.5 | Preserves required visits; unranked science context cannot invent a science utility cost |
| Balanced | `safest` | 1 | Fixed terrain/scenario comparison |

The effective terrain weight is capped at 100. Hard terrain thresholds, unknown
masks and no-corner-cutting rules never relax. Every profile gives nonzero risk
weight to terrain and radiation; an unavailable radiation factor prevents a
comparable route risk. A0 cannot skip a policy-required factor. Optional science
and rover context remain bounded tool choices; the selected profile is included
in the model's compact selection context.

| Resolution | Minimum native factor | Cell cap | Expanded-node cap | Search seconds |
| --- | ---: | ---: | ---: | ---: |
| Coarse | 2 | 131,072 | 100,000 | 5 |
| Standard | 1 | 262,144 | 200,000 | 10 |
| Fine | 1 | 524,288 | 400,000 | 20 |

Host limits further cap these values. Factor one means source resolution, never
super-resolution. Large routes may aggregate more cells. The actual factor,
cell size, host-capped limits and cost parameters are persisted. Regional grids
conservatively aggregate native masks/slopes; all resulting route segments are
independently checked against the native DEM. Coarser grids can exclude narrow
passages and produce longer routes. Cache reuse is separated by policy and bounds.

## Read assessment values correctly

Use **`metadata.assessment.risk_score` and `assessment_confidence` together**.
The versioned traverse-time object remains `metadata.assessment.time`; its total
is also exposed as `result.metrics.estimated_time_min`.

Both assessment scores use 0..100, explicitly identified by `schema_version: "2"` and
`score_scale: "0..100"`. The older `result.metrics.risk_score` remains null and
retains its legacy 0..1 schema; do not put a percentage into that field.

Every assessment includes six factors, including the explicit A5 entry. Internal
IDs join the full specialist public names already present in worker/trace data.
A5 describes the former surface obstacle responsibility merged into the Surface
Traversability and Terrain Hazard Agent; it has explicit zero weights and
`not_applicable` state. No weight is silently reassigned.

The relative factor models are:

- **Surface Traversability and Terrain Hazard Agent:** squared peak conservative
  route slope divided by the host threshold. The factor uses actual checked route
  cells and is bounded to 0..1. It is an engineering utilization measure, not a
  calibrated human accident probability or optical obstacle model.
- **Radiation Exposure and Mission Dose Assessment Agent:** upper sensitivity-band
  scenario dose divided by an explicit user budget, bounded to 0..1. This requires
  a source-identified, scope-matching scenario, applicable duration, uncertainty
  and a budget outcome. Historical replay is hypothetical, not current dosimetry.
- **Thermal Environment and Exposure Context Agent:** unassessed for route risk
  until calibrated observations/model inputs exist.
- **Geological Context and Science Opportunity Agent** and **Rover Traverse and
  Observation Evidence Agent:** context only, never invented safety scores.

`hard_gate_status` precedes aggregation. A failed required scenario is `blocked`;
missing/stale/incompatible/non-assessed weighted factors or required analyses are
`unassessed`. Both yield null comparable risk, with reasons. Terrain blocked or
out-of-source requests retain their HTTP errors and add a string-valued
`hard_gate_status: blocked` detail. A scenario-blocked/unassessed result can retain
its clearly provisional terrain geometry; it is not a feasible mission approval.

For a passing assessment:

```text
risk_score = 100 * sum(profile risk weight * normalized factor risk)
quality = .25 availability + .35 route coverage
        + .20 temporal applicability + .20 validation/provenance
confidence = 100 * sum(profile confidence weight * applicable quality)
             / sum(confidence weights of factors not marked not_applicable)
```

Missing/unassessed/stale/incompatible factors contribute zero confidence even if
some raw components are known. Component values, reasons, evidence IDs, source
URLs, acquisition/observation periods, route coverage (null if unknown), model
versions and weighted contributions are persisted. The frontend renders values;
it does not reproduce the formulas.

Current explicit quality rubric:

- Terrain availability and route coverage are one after complete source/segment
  checks. Unknown acquisition time gives zero temporal quality. A known age over
  3,650 days is stale; future/invalid times are incompatible. That horizon is an
  engineering applicability policy, not a NASA hazard limit. Host-asserted source
  units give 0.5 validation/provenance quality.
- An applicable scenario has complete mission-duration coverage and temporal
  applicability within its explicit hypothetical scope. Validation/provenance is
  0.5 because numerical/provenance checks do not validate transfer to Jezero.
- Usable science/rover context can establish availability and provenance;
  unverified route coverage and mission-time relevance remain zero, not invented.
- Confidence below 70/100 adds an actionable limitations message. This threshold
  controls explanatory copy, not biological safety or permission to ignore gates.

## Persistence and compatibility

Per-leg distances sum to the route total. Per-leg travel/dwell sum to the stored
walking estimate. Source resolution, applied policy and profile version must
match the grid/request/assessment. Public assessment fields match the private
provenance artifact. Corrupt records fail retrieval rather than being rescored.

Old routes without the extension retain null/empty defaults. Interim v1 profile
scores are converted from 0..1 to 0..100 on read and identified by
`legacy-context-quality-v1`; they are not relabelled as v2 factor assessments.
Completed v1 requests that relied on the former implicit `balanced` default can
replay without a new plan/model call. Existing explicit-profile replays retain
their original identity. Failed/unknown legacy inputs are never silently executed
under changed policy; use a new intended request after selecting a supported
profile/objective.

## Independent map registration

`metadata.registration` and `validation.map_alignment` agree and bind to the
source DEM hash, WMTS layer/CRS, hashed capabilities and measurement assets.
Controls require at least four distinct feature observations with spatial spread.
They compare independently measured DEM pixels and WMTS coordinates with wire
coordinates, and restrict applicability to the control convex hull. A route that
leaves that footprint remains unverified.

Tolerance uses pixel quantization plus declared wire/feature uncertainty:

```text
DEM tolerance = hypot(native_dx/2, native_dy/2, wire_uncertainty, feature_uncertainty)
WMTS tolerance = hypot(effective_pixel_size/sqrt(2), wire_uncertainty, feature_uncertainty)
maximum accepted tolerance = min(50 m, 2 * minimum native cell spacing)
```

Effective WMTS pixel size cannot be finer than the actual global tile matrix
geometry. Wrong datum/latitude convention, layer/matrix binding, source hash,
asset hash, insufficient spread, excessive residual/uncertainty or missing inputs
all keep `unverified`. The private provenance keeps a hash-bound control snapshot.
A verified report persists its footprint and residuals for browser inspection.

The current [NASA capabilities document](https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml)
was retrieved read-only and identifies the actual matrix geometry. Its availability
and coordinate arithmetic do not establish common DEM/image features. No real
independent feature measurements were found locally, so production Jezero remains
**unverified**. A subsequent read-only audit covered all five GeoTIFF headers
(each has zero embedded GCPs and no RPC model), the evidence/PLACES files and
the geology archive index. Files named controlled mosaics and their world files
provide georeferencing, not independent NASA-WMTS/DEM feature observations. The coarse global imagery may also fail the fine DEM tolerance;
choosing a different layer requires matching backend configuration, independent
measurements and frontend layer identity.

`verified-alignment-synthetic.json` tests the verified branch only. It is explicitly
synthetic and uses generated capability/measurement assets. Production services
reject synthetic control inputs; only an explicitly injected fixture service can
produce that fixture. Sheng must keep the synthetic label visible during tests
and bind any production overlay to the reported source/layer and verified state.

## Handoff fixtures and commands

`data/fixtures/p1/` contains 19 JSON files: the policy catalog, twelve profile ×
resolution routes, missing radiation, blocked scenario, required unknown thermal,
low-risk/low-confidence, unverified alignment and explicitly synthetic verified
alignment. IDs, wall-clock timing and private-file digests are normalized;
geometry, assessment values, formulas and control results come from the actual
synthetic planner. Re-exporting twice produces byte-identical fixtures.

```bash
cd ~/nasa/repo/A-STELLAR-NASA-Hachathon
conda activate nasa
python scripts/export_p1_fixtures.py
(cd backend && python -m pytest -q)
(cd frontend && npm test && npm run build)
python scripts/verify_p1_workflow.py --dataset-dir "$HOME/nasa/project/dataset"
node scripts/audit_p0_ui.mjs --dataset-dir "$HOME/nasa/project/dataset" --python "$(command -v python)"
python scripts/verify_docker.py --dataset-dir "$HOME/nasa/project/dataset"
python scripts/verify_registration.py --dataset-dir "$HOME/nasa/project/dataset"
```

The registration CLI intentionally exits 2 for `unverified`; provide a request
file and real independent controls to attempt route-specific acceptance. It never
calls a model. Other listed checks are deterministic or use mocked providers.

The remaining joint gate is real independent NASA registration evidence plus
Sheng's P1 presentation and acceptance. Numerical control machinery and synthetic
verified fixtures do not close that real-data gate.

## Observed delivery verification

Verified on 2026-11-15, with zero live generation requests:

- Backend: **418 passed**; frontend: **80 passed**; production build passed.
- P1 real-source matrix: **12 profile/resolution combinations passed**, including
  native-resolution checks, immutable retrieval, replay and fresh-service reads.
  Fine routes measured approximately 61–63 km; conservative coarse/standard
  variants measured approximately 80–95 km. Actual grid sizes were 140, 200 and
  280 m for this particular crater-scale matrix, not the small-walk grid default.
- Production browser recovery suite: **29 checks passed**.
- Eight-stop chat/preview browser suite: **13 checks passed**.
- Actual Docker build/start/restart/recreation: **13 checks passed**, including
  persistent route, assessment, chat and request replay. Its isolated test
  resources were removed.
- The real-source registration diagnostic returned **unverified**, as expected
  without independent feature observations. Synthetic controls cannot enable
  production verification.
- Source DEM SHA-256 remained
  `ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`.

Ignored local evidence under `data/processed/`:

| Verification | Directory |
| --- | --- |
| P1 real-source matrix | `p1-verification/run-20261115T075130Z-4561ba1f` |
| Browser recovery | `p0-ui-audit/run-2026-11-15T07-51-32-506Z` |
| Eight-stop browser | `ui-verification/run-2026-11-15T07-51-32-553Z` |
| Docker | `docker-verification/run-20261115T075127Z-32aa3505384c` |
| Real registration diagnostic | `registration-verification/run-20261115T075021Z-a4463084` |
| Official capabilities inspection | `p1-registration-inspection/capabilities.xml` |
| Local dataset/header/archive audit | `p1-registration-inspection/local-input-audit.json` |

The capabilities response SHA-256 was
`2fb4722b5af0417980052354eab806cb9bdea003617548433cec8d8813d8d125`.
These are local acceptance records, not new source datasets or real registration
certification. Product-level P1 presentation and joint acceptance are still
required before claiming the complete increment.
