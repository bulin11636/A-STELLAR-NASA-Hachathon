# A0 planning, expanded coverage and route chat

Status: implementation and local verification guide, 2026-11-14. See the
[current TODO](TODO.md) for incomplete scientific, map-registration and Docker work.

## Start the application

The backend reads the repository-root `.env` as data without executing shell
commands. `A_STELLAR_ENV_FILE` can select another file; process environment
variables take precedence. No credential value is sent to the browser or saved
in route/chat artifacts. See the placeholder-only [env example](../.env.example).

With `OPENAI_API_KEY` present, the default A0 mode is `agentic`, using
`gpt-6.1-sol`, medium reasoning, Standard service and a 4,096-token output cap
including reasoning. Set `A_STELLAR_A0_MODE=deterministic` for offline routing.
The backend routing mode still defaults to mock unless computed mode is selected.

Install the `planning,agentic` extras in a compatible Python environment. Existing
local dependencies can be reused. Neither LangGraph nor a Codex CLI process is
required for this route/chat adapter; the older optional graph stays separate.

From the repository root, using an activated compatible Python environment:

```bash
cd backend
export A_STELLAR_ROUTING_MODE=computed
export A_STELLAR_DATASET_DIR="/absolute/path/to/dataset"
export A_STELLAR_PLANNING_PROFILE="$PWD/../data/samples/a0-planning-profile.example.json"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root with Node.js 22 available:

```bash
cd frontend
npm run dev -- --force
```

Open the Vite URL, normally `http://127.0.0.1:5173`. Hard-reload after a dependency
cache rebuild. Model/key configuration changes require a backend restart.

In this two-terminal development setup, port 8000 serves the API and port 5173
serves the UI. Opening `http://127.0.0.1:8000/` returns JSON `NOT_FOUND` unless a
production frontend directory was explicitly configured. Check the API at
`http://127.0.0.1:8000/api/v1/health`, and use the Vite URL for route planning.

## Use the UI

1. Check **A0 mode** and the API attempt/cost display. Configuration presence is
   not proof that the provider has accepted the key/model; request errors remain
   explicit. These are application-level provider counters.
2. Use **Load in-coverage example endpoints**, or expand **Enter API coordinates
   and ordered waypoints**. Enter east longitude, planetocentric latitude.
   Put one `longitude, latitude` pair per waypoint line, in required visit order;
   choose **Apply coordinates and stop order** before planning. Up to 16 required
   waypoints are supported. **Load crater-scale example endpoints** selects a
   DEM-derived regional request when supported by the profile.
3. Press **Plan Route**. In computed agentic mode A0 receives compact typed
   evidence, proposes a structured action, and the host runs and validates A*.
4. Read **Planning rationale**, actual metrics, source/policy metadata and the
   **DEM route preview**. The independent preview uses native planning axes and
   does not certify NASA basemap registration or show a terrain-cost raster.
5. In **Discuss this route with A0**, ask why, request `shortest`/`safest`, reorder
   existing waypoints or specify exact new coordinate pairs. Named places must
   resolve to the source-backed catalog; ambiguous names need clarification.
6. An informational answer leaves the route unchanged. An explicit supported
   correction creates a new route ID with a parent link and preserved old result.
   A failed request leaves the previous successful route visible.
   **Changes from previous route** compares persisted distance, objective, stops
   and resolution; incompatible objective costs are not subtracted.
7. The DEM preview initially fits the route. Use **Focus 1** (or another stop),
   **+ / −**, dragging and **Fit route** to inspect nearby locations separately.

The chat can use the language of the user's message. Free-form avoidance-area
polygons, arbitrary slope-limit changes and unconstrained itinerary optimization
are not implemented. The ordered coordinate editor works without a live model;
in deterministic mode chat explains the stored result and directs changes to
that editor rather than pretending to perform natural-language replanning.

NASA overlay registration remains unverified, so computed geometry stays off
the basemap. Existing remote layer/point-evidence/briefing panels are integrated;
their fixture-scoped context is distinct from evidence used by backend A0.

## Expanded planning coverage

The seed CTX profile remains a 128-by-128 window for its reproducible example.
With `dynamic_windowing: true` (default), route stops outside that window trigger
a new native-resolution source crop with a configurable pixel margin and halo.
All requested waypoints participate in cropping. The example profile permits
one million cells, 500,000 expanded nodes and 15 seconds shared across A* legs.

Requests exceeding the native crop allocation switch to the full supported
source at an adaptive search resolution. Streaming native windows preserve
derivatives before aggregation: any unknown or blocked constituent blocks the
entire search cell. The CTX source fits at 100 m search spacing from 20 m native
data. After planning, an independent native-pixel intersection validator re-reads
every touched part of the source. The source is never modified or smoothed.

This supports crater-scale routes within the approximately 89-by-101 km source.
Aggregation can exclude narrow native corridors; optimality applies to the
selected search graph. Partial edge blocks, missing derivative halos, NoData and
blocked cells remain unavailable. Outside-source stops return
`OUTSIDE_PLANNING_COVERAGE`; search/adaptation limits remain explicit. Set
`adaptive_resolution: false` to retain native-only allocation behavior.
Disconnected native crops receive one full-source retry under the original
node/time budget without another model call.
Refining excluded narrow passages and combining the other DEMs remain pending.

## Evidence and model usage

A1 evidence comes from the validated terrain pipeline. A configured
`A_STELLAR_EVIDENCE_PROFILE` can supply additional workers through the existing
typed registry. Otherwise, exactly one verified local snapshot under the DEM's
sibling `evidence/jezero-evidence-*/manifest.json` can supply A4/A6 context. Multiple
snapshots require explicit selection. Normalized artifacts are written to ignored
output storage, leaving raw inputs in place. No request downloads data.

Science/rover outputs remain contextual; thermal and radiation inputs without
configured validated models remain unavailable. A0 cannot invent a missing
assessment or silently turn historical observations into per-cell safety costs.

Each normal Plan Route or chat request makes at most one model request and does
not retry paid generation automatically. The application checks a conservative
6,000-byte serialized payload budget, including prompts/tools, with reserved
protocol headroom; this is not an exact tokenizer measurement. Actual provider
token usage is saved after response. Output is capped at 4,096 tokens including
reasoning. Incomplete output is an error, not a trigger to increase the budget.

A persistent SQLite ledger applies the configured request and cost limits before sending.
`A_STELLAR_A0_USAGE_STORE` selects persistent ledger storage independently of route
output, so changing the route output directory does not reset model accounting.
Timeouts/unknown charges retain reservations. Do not delete the ledger to bypass
the configured limits.

Other models need an explicit supported adapter rather than a silent switch.
Chat message IDs prevent duplicate automatic generation; replaying a
failed/in-progress ID produces a conflict instead of another paid call.

## API additions

- `PlanRouteRequest.waypoints`: optional ordered list, maximum 16 coordinates.
- `GET /api/v1/regions`: initial bounds, source bounds, dynamic-window capability,
  configured cell limit and optional example request.
- `GET /api/v1/a0/status`: agent mode/model and estimated/reserved API budget.
- `POST /api/v1/routes/{route_id}/chat`: `{message, request_id}`; returns a reply,
  optional validated revision result/metadata and usage.
- `GET /api/v1/routes/{route_id}/chat`: bounded persisted current/ancestor history
  (latest 40 messages across at most 12 parent revisions).

Route metadata now includes nullable `rationale`, `usage` and `parent_route_id`.
Older stored records parse with default values. Regenerate browser types and
stored-route/chat schemas with `python -m app.planning.export_contract`.

## Verification commands

From the repository root, the default uses real DEM data and a mocked model:

```bash
/home/sam/miniconda3/envs/nasa/bin/python scripts/verify_agent_workflow.py
```

An explicitly paid verification uses the private backend credential and makes
at most three requests (plan, question, waypoint revision):

```bash
/home/sam/miniconda3/envs/nasa/bin/python scripts/verify_agent_workflow.py --live-model
```

Reports go under ignored `data/processed/a0-workflow/`. Failures stop the sequence;
mocked usage is synthetic and must not be described as actual API billing.
The older `app.planning.verify` command now explicitly forces deterministic A0
mode for its server, even when a private `.env` exists.
