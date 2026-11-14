# Development setup

Use Python 3.10 (the pinned scientific wheels do not currently install on this workspace's Python 3.14) and Node.js 22+. Commands use PowerShell and avoid activation scripts. Run the backend and frontend in separate terminals.

## Backend

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-dev.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Development dependencies include pinned packages for Sheng's evidence workers. The `planning` extra supplies NumPy, rasterio and pyproj for deterministic routing. Use `.[dev,planning]` with the Python 3.10 constraints for a combined development install. Large GeoTIFFs stay at their [configured local location](datasets.md).

The development extra also installs pinned LangGraph dependencies for A0. A smaller agentic install can use `pip install -c constraints-dev.txt -e ".[a0]"`; scientific profiles may additionally need `.[evidence]`/`.[geology]`. Existing FastAPI startup does not import LangGraph. See [A0 commands and the new-chat test prompt](agents.md#a0--agentic-mission-coordinator).

- Health: http://127.0.0.1:8000/api/v1/health
- API documentation: http://127.0.0.1:8000/docs
- Schema: http://127.0.0.1:8000/openapi.json

## Frontend

From the repository root:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open the URL printed by Vite, normally http://localhost:5173. Vite proxies `/api/v1/...` to FastAPI on port 8000. NASA WMTS requests go directly to NASA. Production needs an equivalent same-origin reverse proxy.

Choose **View Jezero area**, **Pick Start**, then select Start and Goal. Planning requires FastAPI; failures are displayed without a client-generated route. Mock results retain their label. Computed API results show distance, provenance and policy; computed map geometry remains hidden until scientific map/wire alignment is validated. Map picks retain their visible unverified-coordinate caveat.

## Deterministic computed routing on Linux

For a minimal deterministic environment, install from `backend/`:

```bash
python -m pip install -e '.[planning]' pytest==9.2.0 httpx==0.28.1
```

This path does not install LangGraph. Python 3.13.14 with newer compatible
scientific wheels was used for the recorded Linux run; the older Python 3.10
development constraints were preserved. See the report for exact versions.

With the supplied DEM already present, configure the server from `backend/`:

```bash
export A_STELLAR_ROUTING_MODE=computed
export A_STELLAR_DATASET_DIR="$HOME/nasa/project/dataset"
export A_STELLAR_PLANNING_PROFILE="$PWD/../data/samples/a0-planning-profile.example.json"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The sample profile is specific to the inspected CTX raster/window, not arbitrary
similarly named DEMs. Source CRS, metre interpretation, resolution and masks
must be checked when replacing it. Records default to `data/processed/routes`.
Use the [verification guide](a0-verification.md#implemented-local-verification-command)
for the explicit real DEM/API/restart command and exact request.

### Avoiding out-of-coverage selections

Restart the backend after code changes, then reload the frontend. The route
panel reads planning information from `GET /api/v1/regions`. The CTX
profile starts with a 128 by 128 cell example window (2.56 by 2.56 km).
Use **Load in-coverage example endpoints**, then **Plan Route**, to submit the
same DEM-derived endpoint cells used by the real-data verifier. This works
without NASA tiles loading. The example is advertised only for the matching
CTX demo window with allowed endpoint cells. **Load crater-scale example
endpoints** selects a separate regional request when the source supports it.
Dynamic crops cover other supported source locations; requests exceeding the
native allocation use conservative aggregation and independent native segment
validation. See the [regional guide](regional-verification.md) for coverage and
resolution limits. Other profiles do not inherit assumed CTX coordinates.

Bounds describe coverage, not guaranteed traversability or connectivity. Map
clicks retain their unverified-coordinate caveat, and computed map geometry
stays hidden pending registration evidence.

### Missing Vite optimized dependency chunks

After dependency or source changes, restart the frontend with:

```bash
cd frontend
npm run dev -- --force
```

The force option rebuilds Vite's optimized dependency cache. Hard-reload the
browser afterwards; if it still requests an old chunk, enable **Disable cache**
in browser DevTools and reload. The development config explicitly prebundles
React's JSX runtimes to avoid discovering them only after the page loads.
Do not exclude React from optimization to work around a stale chunk reference.

## Checks

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.coordinator.demo
```

From `frontend/`:

```powershell
npm.cmd test
npm.cmd run build
```

The frontend build includes TypeScript checking. Use `npm` instead of `npm.cmd` on other shells, and `.venv/bin/python` for a POSIX environment. Existing Starlette/httpx deprecation and frontend bundle-size warnings are non-fatal.

A1/A2 package/adaptor tests use synthetic runners and verify async dispatch, context checks and prototype labeling. Real raster execution remains a separate check requiring their dependencies and data.
