# Specialist selection and walking assessment

This extends the [P0 UI delivery](P0_UI_ACCEPTANCE.md) and is delivered on `main`. The web API retains the
actual terrain A* service, immutable route records and explicit recovery protocol.
The separate experimental CLI graph is not the web planner and still retains
its original planner-availability gate.

## Request flow and boundaries

1. The host checks DEM coverage and planning configuration before generation.
2. When optional workers are configured, A0 receives a compact capability catalog
   and returns one bounded selection covering every optional specialist.
3. The host always requires terrain assessment. Typed user-required analyses also
   cannot be skipped. Unconfigured required analyses remain explicitly unassessed.
4. Selected Python workers execute through the existing registry and dispatcher.
   Only typed, source-identified observed/scenario outputs can enter model facts.
   Failed, unavailable, mock and source-less outputs are not valid citations.
5. A0 returns one explanation or bounded route proposal. Python computes A*, checks
   exact endpoints and visit order, and independently checks native terrain cells.
6. The host computes walking time from explicit assumptions, then evaluates a
   selected, configured radiation scenario using its applicable exposure duration.
7. Route metadata and chat responses expose the specialist trace. Private audit
   artifacts retain raw evidence; source paths and credentials stay off the wire.

| Internal ID | Public specialist | Current application |
| --- | --- | --- |
| A1 | Surface Traversability and Terrain Hazard Agent | Mandatory DEM coverage, slope costs and native terrain checks |
| A2 | Thermal Environment and Exposure Context Agent | Configured prototype context only; calibrated thermal constraints remain unknown |
| A3 | Radiation Exposure and Mission Dose Assessment Agent | Explicitly configured constant-rate dose scenario; no spatial radiation cost |
| A4 | Geological Context and Science Opportunity Agent | Source-grounded science context and waypoint suggestions; no invented priority score |
| A6 | Rover Traverse and Observation Evidence Agent | Historical rover context; no inference that a past traverse proves current safety |

The former surface obstacle responsibility (A5) is merged into the Surface
Traversability and Terrain Hazard Agent. Optical obstacles remain unassessed.

`GET /api/v1/a0/capabilities` inspects local configuration without generation.
It reports configuration, purpose, mandatory terrain policy, walking mode and the
maximum per-action model-call count. Configured does not mean calibrated or usable
for the current scope. The saved trace distinguishes selection source/reason,
execution (including cache hits), result quality (`partial` versus `ready`), data
kind, application, constraint status and audit reference.

## Configuration and remaining scientific work

With exactly one verified local evidence manifest beside the DEM, science and
rover workers can be discovered automatically. An explicit
`A_STELLAR_EVIDENCE_PROFILE` instead supplies a trusted local runtime profile;
see [agent configuration](agents.md#package-interface-for-a0) and
[profile documentation](agents.md). Supported profile fields include the evidence
manifest, optional geology/observation reports, thermal configuration and radiation
scenario. Paths resolve relative to their configuration files. Every worker must
match the declared region, ROI and dataset version. Missing/invalid profiles do
not trigger downloads or silent fallback to a different release.

The tracked `data/samples/a0-profile.json` demonstrates the historical radiation
scenario only; it does not implicitly include the local science/rover snapshot.
Combining inputs requires an explicitly compatible profile. Downloading thermal
mosaics does not calibrate them, and downloading RAD detector records does not
create a Jezero EVA dose-equivalent model. This delivery does not invent either
model or silently relabel the historical scenario as an observation.

## Walking assumptions and API extension

Walking is the only mission mode. Advanced mode accepts an optional `mission`
object on `POST /api/v1/routes/plan`:

```json
{
  "mode": "walking",
  "speed_m_s": 1.0,
  "stop_minutes_per_waypoint": 3.0,
  "exposure_duration_min": null,
  "radiation_budget_usv": null,
  "required_analyses": ["A2", "A3"]
}
```

The speed above is an input example, not a default or recommended Mars walking
speed. A blank speed leaves Estimated time unknown. Explicit zero dwell means no
intermediate stop allowance. Time equals native projected route distance divided
by the supplied speed, plus dwell once per required intermediate visit. Start and
goal dwell, slope-dependent speed, rest, suit/load and physiology are excluded.
Input bounds are engineering limits, not physical recommendations. The route
reader rejects time records inconsistent with their distance or assumptions.

A supplied exposure duration overrides the computed total for the radiation
scenario. Otherwise, the scenario uses the walking estimate. Without either,
dose remains unknown. A dose budget makes radiation analysis required; it does
not supply a missing model. Scenario `pass`, `fail` and `unknown` apply only to the
configured sensitivity band, never to astronaut safety. A missing required
analysis or failed required scenario produces a clearly provisional terrain route
with explicit warnings, not a claim that all mission constraints passed.

Chat revisions preserve the typed mission assumptions and recompute time and
scenario exposure for the new route. Speed/budget editing is currently through
the Advanced controls and a new plan; free text cannot mutate those typed fields.
Free-text analysis requests guide selection, while the Required analyses controls
provide the host-enforced requirement. Combined risk has no calibrated model and
remains `null`, displayed as **Not assessed**.

The existing plan response shape is retained. Stored metadata adds `assessment`
and `specialist_trace`; chat responses add `specialist_trace`, including replies
without revisions. Old stored records load with empty/null defaults and are
serialized in the new shape. Deploy the regenerated frontend and backend together.
Missing versus explicit-null mission retains legacy plan-request identity.

## Bounded model usage and recovery

An action makes at most two model requests: selection and final proposal. With
no configured optional worker, selection is omitted and only the final request
runs. Advanced Plan and Ask A0 contains two actions, so its upper bound is four
model requests. Deterministic mode makes none; required Python analyses can still
run. Existing global request/cost caps and the conservative input guard remain.

Successful selection is durably checkpointed against the action input, capability
catalog and evidence version. A permitted manual retry after a final-stage 429
reuses that checkpoint, including across process restart. Unknown outcomes never
permit automatic paid retry. Corrupt/mismatching checkpoints stop without a new
selection call. Global usage includes failed/reserved calls; a successful route's
usage records its successful selection and final proposal. Cached/replayed HTTP
responses make no generation requests.

Worker outputs use a bounded in-process cache keyed by scope, evidence version,
parameters and configured raster size/mtime. This is a cache, not scientific
certification. Restart discards it; raw inputs must remain immutable during a run.
Python workers and numerical assessments do not invoke additional language models.

## Reproduce offline verification

```bash
cd ~/nasa/repo/A-STELLAR-NASA-Hachathon
conda activate nasa
(cd backend && python -m pytest -q)
(cd frontend && npm test && npm run build)
node scripts/audit_p0_ui.mjs --dataset-dir "$HOME/nasa/project/dataset" --python "$(command -v python)"
node frontend/tests/browser-workflow.mjs --dataset-dir "$HOME/nasa/project/dataset" --python "$(command -v python)"
python scripts/verify_regional_workflow.py --dataset-dir "$HOME/nasa/project/dataset"
python scripts/verify_agent_workflow.py --dataset-dir "$HOME/nasa/project/dataset"
python scripts/verify_docker.py --dataset-dir "$HOME/nasa/project/dataset"
```

Browser acceptance requires Playwright's Chromium. These commands mock every model
response or use deterministic mode; no live-model flag is needed. The optional
`verify_agent_workflow.py --live-model` path keeps its default four-call cap and
checks the full workflow's required allowance before generation. When configured
optional tools require eight calls, a user must explicitly provide
`--max-live-calls 8`; shared caps still apply. This phase ran no live calls.

## Manual UI walkthrough

Start the current checkout with:

```bash
python scripts/run_docker.py --env-file "$PWD/.env" \
  --dataset-dir "$HOME/nasa/project/dataset" --mode agentic
```

Open `http://127.0.0.1:8080`. Choose Advanced, load the in-coverage example, enter
an assumed speed and dwell, select an analysis focus and enter requirements.
Optionally mark thermal/radiation analysis required to inspect truthful missing
inputs. Plan and Ask A0 stores the base route before asking for interpretation.
Inspect Walking time and exposure assumptions, Planning rationale and Specialist
selection and execution. Add ordered stops, then ask chat to reverse the waypoint
visits or add explicitly supplied longitude,latitude coordinates. Each actual
agentic action uses the configured provider and budget.

The DEM preview supports stop focus, zoom, pan and route fitting. Computed lines
remain withheld from the NASA basemap until independent registration is verified.

## Observed acceptance

Verified on 2026-11-15 in `sam/backend`, based on merged main `87238e3`:

- Backend: **381 passed**; frontend: **77 passed**; production build passed.
- Production browser acceptance: **29 checks passed**, including explicit speed
  and dwell, required missing analysis, tool traces, ordered chat revisions,
  manual retry/recovery and reload/restart behavior.
- Existing browser workflow: **13 checks passed**, including eight-stop additions
  and reversal, comparison, focus, zoom, pan and expanded preview.
- Regional API workflow: **10 checks passed**, including multiple directions and
  native checks for the approximately 60.04 km crater-scale example.
- Four-action agent workflow: **9 checks passed**, using eight mocked provider
  requests for tool selection and final proposals.
- Final Docker workflow: **13 checks passed**, including walking estimates,
  required unknown radiation, capability inspection, restart/recreation and
  persistent replay. Its temporary containers, volume and test image were removed.
- **Zero live model calls** in this phase. Source DEM bytes remained unchanged
  (`ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`).

Ignored local evidence directories under `data/processed/`:

| Workflow | Directory |
| --- | --- |
| Current browser | `p0-ui-audit/run-2026-11-15T06-09-36-202Z` |
| Existing browser | `ui-verification/run-2026-11-15T06-03-54-170Z` |
| Regional API | `regional-verification/run-20261115T060313Z-41eab59a` |
| Agent workflow | `a0-workflow/run-20261115T060540Z-fadfae90` |
| Final Docker | `docker-verification/run-20261115T060932Z-a84da8941ed8` |

Each contains a `summary.json`; browser runs also contain screenshots. These are
local evidence paths, not tracked datasets or operational safety certification.
