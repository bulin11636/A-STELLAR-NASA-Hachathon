# Verification

Use this guide to reproduce checks against the current checkout. Historical
per-person delivery logs and stage-specific handoffs are not the maintained test
reference. Source manifests and scientific records remain in `data/samples/`;
small test fixtures remain in `data/fixtures/`.

## Unit tests and build

In the full development environment described in [setup](setup.md):

```bash
cd backend
python -m pytest -q
```

In a separate terminal, from the repository root:

```bash
cd frontend
npm ci
npm test
npm run build
```

The build includes TypeScript checking. CI runs backend and frontend checks and
an isolated Docker workflow with a generated synthetic DEM. A passing synthetic
suite does not certify a real raster or NASA alignment.

## Generated contracts and fixtures

From `backend/`, regenerate frontend contracts after changing backend models:

```bash
python -m app.planning.export_contract
```

Review generated schema/type changes together with the backend changes. Tests
cover backward compatibility and interpretation of partial/complete assessments.
The canonical synthetic P1 fixture exporter is:

```bash
python scripts/export_p1_fixtures.py
```

Run it from the repository root. These are synthetic fixtures, not observations;
review changes before committing them. Keep raw data and ignored runtime reports
out of commits.

## Real DEM workflows without live model calls

From the repository root, with the configured CTX DEM available:

```bash
python scripts/verify_regional_workflow.py --dataset-dir /absolute/path/to/dataset
python scripts/verify_p1_workflow.py --dataset-dir /absolute/path/to/dataset
python scripts/verify_agent_workflow.py --dataset-dir /absolute/path/to/dataset
```

These exercise regional crops/aggregation, native checks, policies, ordered
revisions and stored metadata with deterministic or mocked provider responses.
They write isolated reports under ignored `data/processed/` paths.
The agent workflow does not use a live model unless explicitly requested.

Live generation is a separate opt-in exercise. `--live-model` on the agent
workflow can incur provider usage and requires an explicit sufficient call cap;
its shared application allowance still applies. Never infer successful live
provider access from mock tests or a model-list response.

## Browser workflows

Build the frontend first and install Playwright Chromium if needed:

```bash
cd frontend
npx playwright install chromium
```

From the repository root:

```bash
node frontend/tests/browser-workflow.mjs --dataset-dir /absolute/path/to/dataset --python /absolute/path/to/python
node frontend/tests/browser-ui-regressions.mjs --dataset-dir /absolute/path/to/dataset --python /absolute/path/to/python
```

The scripts start and stop their own local API servers and use mock model
responses. The route workflow blocks NASA access and checks ordered-stop edits,
route history, preview navigation and a regional route.

The UI regression workflow needs real local DEM/optional inputs plus
`registration/jezero-wmts-capabilities.xml` in the dataset root. It tests layer
controls, raster delivery, geology when configured, briefing layout and request
recovery. It mocks NASA tiles by default. Add `--live-nasa` to exercise actual
NASA imagery delivery; that flag does not enable live model generation.
`--channel chrome` can select an installed Chrome browser instead of Playwright's
bundled Chromium. A cached capabilities file is a test/reference asset, not
independent registration evidence.

The older `scripts/audit_p0_ui.mjs` targets a historical layout and is not the
current main-branch browser acceptance entry point.

## Docker acceptance

With Docker running, from the repository root:

```bash
python scripts/verify_docker.py --synthetic
```

For real terrain inputs:

```bash
python scripts/verify_docker.py --dataset-dir /absolute/path/to/dataset
```

The verifier builds the image, starts an isolated Compose project, checks
readiness/mounts, creates terrain and chat records, and checks them after restart
and recreation. It uses deterministic mode, generates no model responses and
removes its own temporary container/volume/image resources unless instructed to
keep them. It does not remove an unrelated deployment's state. `--prepare-only`
prepares inputs but is not an actual container run.

Read reports for the exact dataset, mode, source hash, checks and outcome.
A successful container check does not establish scientific validity or provider
eligibility. Do not report old test totals as results for a newer checkout.

## Registration and scientific acceptance

Use [map registration](map-registration.md) to collect independent feature
measurements and run `scripts/verify_registration.py`. Real controls must match
the source, NASA layer/CRS and route scope; synthetic controls do not establish a
production verified outcome. Registration, terrain-model validation, environmental
model calibration and actual astronaut suitability are separate questions.
