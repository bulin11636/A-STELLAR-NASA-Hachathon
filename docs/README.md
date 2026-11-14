# Documentation

| Guide | Contents |
| --- | --- |
| [Current TODO](TODO.md) | Known defects, model-assisted A0, route chat/preferences, planning rationale, broader ROI and Docker env-file roadmap |
| [A0 agent and chat guide](a0-agent-chat.md) | Start the metered A0 workflow, enter ordered stops, inspect dynamic DEM routes and use persistent chat revisions |
| [Earlier ROI/chat checkpoint](a0-agent-chat-verification.md) | Historical delivery, browser evidence and the HTTP 429 live-provider blocker |
| [Setup](setup.md) | Installation, development and tests |
| [Docker runtime](docker.md) | External configuration, read-only datasets, persistent state and readiness |
| [Provider diagnostics](provider-troubleshooting.md) | Safe HTTP 429 classification and local/GET-only troubleshooting |
| [Regional verification](regional-verification.md) | Adaptive crater-scale routing, multi-stop revisions and reproducible production browser checks |
| [Architecture](architecture.md) | Current components, implementation stages and A0 gates |
| [Agents](agents.md) | A1/A2 usage and A3/A4/A6 previews, results and limitations |
| [Datasets](datasets.md) | Data locations, filenames, sources and provenance |
| [API protocol](A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md) | Authoritative frontend/backend wire contract |
| [Team master plan](A_STELLAR_JEZERO_TEAM_BACKEND_MASTER_PLAN.md) | Ownership, milestones and acceptance requirements |
| [A0 implementation plan](a0-implementation-plan.md) | Approved deterministic A*, full public agent names, local inputs and completion gates |
| [A0 API addendum](a0-api-contract.md) | Target computed-mode behavior, persistent route retrieval and metadata schema |
| [A0 verification](a0-verification.md) | Synthetic, real DEM, API persistence, frontend and optional graph checks |
| [A0 new-chat prompt](a0-new-chat-prompt.md) | Copyable English implementation/test handoff and verification-only guidance |
| [A0 frontend integration](a0-frontend-integration.md) | Fetched remote baseline, local work preservation, frontend boundaries and integration checks |
| [A0 verification report](a0-verification-report.md) | Actual resumed implementation, remote reconciliation, real DEM/API/restart results and pending display acceptance |

Setup guides and overlapping agent reports are merged here. Scientific fixtures live in `data/fixtures/`; documentation contains no datasets. The repository-root README is the entry point.

Implemented API endpoints: `GET /api/v1/health`, `GET /api/v1/ready`, `GET /api/v1/regions`, `POST /api/v1/routes/plan`, `GET /api/v1/routes/{route_id}`, `GET /api/v1/a0/status`, and `GET/POST /api/v1/routes/{route_id}/chat`. Routing defaults to mock; explicit computed configuration enables validated terrain planning and durable retrieval. Live schemas are available at FastAPI's `/docs` and `/openapi.json`.

The `a0-*` documents preserve the approved scope and handoff. The implementation and API addendum are now exercised on a real CTX ROI; computed browser display remains pending alignment verification.
