# Regional planning and browser acceptance

The CTX profile supports the full configured source interior through native
dynamic crops and conservative adaptive search grids. This remains terrain-only
research planning. Covered points can still be blocked, unknown, disconnected or
excluded by aggregation; coverage does not guarantee a feasible route.

## Planning strategy

Small requests retain native resolution. If the endpoint/waypoint crop exceeds
the allocation limit, the planner uses the full source at the smallest integer
aggregation factor that fits the search-cell budget. The example CTX source
uses 100 m search cells derived from 20 m native cells. Native reads stream in
tiles bounded to 512 by 512 cells plus derivative halos.

Slope is calculated before aggregation. A coarse cell is traversable only when
all constituent native cells are covered, known and below the slope limit. Its
penalty uses maximum native slope. Partial edge blocks remain unknown. A*
preserves exact endpoints, ordered stops, forbidden diagonal corner cuts and a
shared search budget across legs.

Closed-cell segment checks validate emitted geometry. For aggregated grids,
a separate source validator re-reads native pixels along every segment and
rejects touched unknown/blocked pixels, including corner touches. Reports and
source hashes are persisted. Retrieval checks the aggregation factor against
source windows, affine coefficients, dimensions and resolution. Original
native-grid records remain readable.

Disconnected native crops receive one full-source retry sharing the original
node/time budget and model proposal. This strategy does not refine every narrow
passage or establish native-grid or continuous-space optimality. Missing data,
adaptive limits and search exhaustion stay explicit.

## Reproduce

Use a compatible Python environment with backend `planning,agentic` extras,
pytest for backend tests, and Node.js 22. From the repository root:

```bash
cd frontend
npm ci
npm test
npm run build
npx playwright install chromium
cd ..
python scripts/verify_regional_workflow.py --dataset-dir /absolute/path/to/dataset
cd frontend
npm run test:browser -- --dataset-dir /absolute/path/to/dataset --python /path/to/python
```

On supported Linux environments, Playwright OS dependencies can be installed
with `npx playwright install --with-deps chromium`. Run backend checks from
`backend/` with `python -m pytest -q`. Rebuild the UI before browser verification.
Regenerate metadata contracts with `python -m app.planning.export_contract` in
`backend/` after contract changes.

Both verifiers explicitly mock model responses and make no live generation
requests. They test actual A*, source evidence, contracts, structured proposal
application and durable state. The browser serves production UI/API together
and blocks external requests. These checks do not establish live-model language
understanding, provider access or NASA registration.

## Verified local results

The CTX source SHA-256 is
`ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`.
It covers approximately 89 by 101 km. The diagonal demonstration produced a
60,038.90 m projected route on a 1,013 by 891 grid at 100 m spacing, followed by
independent 20 m native checks. Source bytes were unchanged. Forward/reverse
routes, eight-stop additions, reversed order, explanation without revision and
fresh-service retrieval/history passed. Additional real-source routes passed
the other diagonal (60,556.05 m), north/south (65,101.43 m) and terrain-weighted
mode (62,176.15 m). These are projected polyline lengths under the research policy.

The production browser passed planning/rationale display, adding two then six
stops, reversing eight visits, parent comparison, reload recovery, nearby-stop
focus, zoom/pan, expansion/explicit close and crater-scale route display. Model calls were mocked and
external NASA requests were blocked.

The latest local suites passed 309 backend tests and 48 frontend tests. The
production build passed without the earlier oversized-chunk warning; Affine
operator warnings were removed from planning and its tests. React renderer
deprecation remains a test-maintenance task.

Ignored machine-generated evidence under `data/processed/`:

- Regional API: `regional-verification/run-20261115T000026Z-dca13878/summary.json`.
- Browser: `ui-verification/run-2026-11-15T00-02-08-504Z/summary.json`.
- Screenshots: that browser run's `eight-stops.png`, `regional-route.png` and `ui.png`.

The UI supports up to 16 required ordered waypoints. **Load crater-scale example
endpoints** uses DEM-derived demo positions when both targets are source-covered.
Use preview fit/focus/zoom/pan/expand controls to inspect results. Computed NASA
overlays remain gated pending independent registration controls.

The selected live-provider workflow and actual Docker build/mount/restart tests
have passed; see the [current checkpoint](backend-verification.md) for evidence
and boundaries. Independent NASA alignment and final frontend presentation
validation remain separate. See the [TODO](TODO.md) for pending work only.
