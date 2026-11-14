# A-STELLAR

Jezero exploration prototype: React/TypeScript with NASA Mars Trek imagery, FastAPI, deterministic DEM-based A* routing, an optional agentic A0 experiment, prototype A1/A2 and source-backed A3/A4/A6 workers. Routing defaults to explicit mock mode; configured computed mode persists validated terrain routes and metadata. Computed map geometry remains hidden pending NASA map registration.

```text
frontend/             React UI, NASA map and typed API client
backend/app/
  api/                FastAPI endpoints
  contracts/          API and worker schemas
  coordinator/        A0 dispatcher and mission coordinator
  agents/             a1/a2/a3/a4/a6 packages, async workers and registry
  evidence/           Shared scientific utilities and offline previews
  geo/, planning/     Terrain and route integration
backend/tests/        Backend tests
data/                 All datasets, fixtures and scientific artifacts
docs/                 All project documentation
.github/workflows/    CI
```

Start with [setup](docs/setup.md), [agents](docs/agents.md), [data locations](docs/datasets.md) and [architecture / A0 next steps](docs/architecture.md). See the [documentation index](docs/README.md) for the authoritative API and team plans.

Backend work on `sam/backend` follows the [backend handoff](docs/backend-handoff.md),
including portable startup, explicit request recovery and Docker verification.

See the [current TODO](docs/TODO.md) for remaining work. The
[Docker guide](docs/docker.md) covers external runtime configuration and persistent
state. [Regional verification](docs/regional-verification.md) covers crater-scale
planning, multiple waypoint revisions and browser acceptance.

The [agent and chat guide](docs/a0-agent-chat.md) covers the expanded-ROI workflow,
backend `.env`, GPT-6.1 Sol defaults, API usage limits, ordered waypoints, route
explanations and persistent conversational revisions. Computed NASA overlays
remain gated; the UI includes an independent DEM-axis route preview.

The [A0 verification report](docs/a0-verification-report.md) records real local DEM/API/restart results, exact requests and remaining display acceptance gates. See the [verification guide](docs/a0-verification.md) for a reproducible command and the preserved [English handoff](docs/a0-new-chat-prompt.md) for the approved scope.
