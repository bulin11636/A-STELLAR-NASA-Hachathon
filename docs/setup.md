# Development setup

For the production UI and API in one container, start with [Docker](docker.md).
This guide covers native development. Commands run from the repository root
unless a different directory is shown.

## Prerequisites

- Node.js 22 or later and npm for the frontend.
- Python 3.10 for the full development dependency set used by CI.
- The configured local DEM for computed routing; see [datasets](datasets.md).

The Docker/runtime dependency set targets Python 3.13. It is maintained separately
in `backend/constraints-runtime.txt`. Do not apply the Python 3.10 development
constraints to an arbitrary newer interpreter and assume compiled wheels match.

## Create a development environment

Bash / WSL:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -c backend/constraints-dev.txt -e './backend[dev,planning,agentic]'
```

PowerShell:

```powershell
py -3.10 -m venv .venv
./.venv/Scripts/python.exe -m pip install -c backend/constraints-dev.txt -e "./backend[dev,planning,agentic]"
```

PowerShell commands can use `./.venv/Scripts/python.exe` directly without
activating an environment. Use an existing compatible environment if one is
already installed.

For a smaller Python 3.13 planning/runtime environment:

```bash
python -m pip install -c backend/constraints-runtime.txt -e './backend[planning,agentic]'
```

This smaller install does not include every optional geology or experimental
graph dependency. A missing optional layer/worker must remain unavailable.

## Prepare private configuration

Copy `.env.example` to an untracked `.env` and edit the runtime values. Do not
put credential values into tracked files, frontend code or command-line arguments.
Explicit launcher arguments select this checkout's dataset, profile and state
paths. An API credential is needed for agentic mode; deterministic mode does not
make model-generation requests.

The default sample profile expects `M20_JezeroCrater_CTXDEM_20m.tif` immediately
inside the supplied dataset directory. A file name alone is not enough to
validate a replacement DEM.

## Start the backend

Use the Python environment prepared above:

```bash
python scripts/run_backend.py --dataset-dir /absolute/path/to/dataset --env-file .env --mode deterministic --check
python scripts/run_backend.py --dataset-dir /absolute/path/to/dataset --env-file .env --mode deterministic
```

`--check` validates local configuration without starting the server or contacting
the provider. Change the mode to `agentic` when the runtime key and provider
access are configured. Local readiness does not prove API credit or generation
eligibility.

- API health: <http://127.0.0.1:8000/api/v1/health>
- Local readiness: <http://127.0.0.1:8000/api/v1/ready>
- Interactive API reference: <http://127.0.0.1:8000/docs>

`--state-dir /path/to/state` selects persistent native state. Otherwise the
launcher uses this checkout's ignored `data/processed/` directory. Runtime
configuration changes require restarting the backend.

## Start the frontend

In another terminal:

```bash
cd frontend
npm ci
npm run dev -- --force
```

Open the Vite URL, normally <http://localhost:5173>. Vite proxies `/api` to
port 8000; the API root on port 8000 is not the development webpage. Stop an old
checkout's server before reusing the same ports.

Load the backend-provided in-coverage example in Plan and choose Plan Route.
For an agentic walkthrough, use Mission Planner to ask a reason or request a
supported revision. Advanced adds ordered stops and explicit walking assumptions.

## Common development issues

| Symptom | Check |
| --- | --- |
| Vite references a missing optimized dependency chunk | Restart with `npm run dev -- --force`, then hard-refresh the browser |
| API/proxy connection fails | Start the matching backend on port 8000 and inspect `/api/v1/ready` |
| Computed routing is unavailable | Check the profile, DEM path, native dependencies and state permissions |
| A selected stop is outside planning coverage | Use the advertised source footprint or a DEM-derived example; image coverage is different |
| Thermal/geology layer does not appear | Check its source file and optional dependencies; see [datasets](datasets.md) |
| A0 fails with 429/503 or an invalid proposal | Follow [provider troubleshooting](provider-troubleshooting.md) |

Tests and generated-contract checks are documented in [verification](verification.md).
