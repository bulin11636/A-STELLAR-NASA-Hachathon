# Documentation

| Guide | Contents |
| --- | --- |
| [Specialist selection and walking assessment](SPECIALIST_ROUTING_AND_WALKING.md) | Bounded tool selection, auditable traces, explicit walking time, scenario assessment and offline verification |
| [Current TODO](TODO.md) | Remaining demo handoff checks and deferred exploration; pending tasks only |
| [P0 UI acceptance and walkthrough](P0_UI_ACCEPTANCE.md) | Completed integration fixes, Docker startup, real-data manual steps and acceptance results |
| [Merged P0 integration gaps](P0_INTEGRATION_GAPS.md) | Historical merged-main findings, now resolved by the P0 UI delivery |
| [Sam P0 backend delivery](P0_BACKEND_DELIVERY.md) | Advanced context, durable recovery, runtime status, shared fixtures and observed acceptance |
| [Backend handoff](backend-handoff.md) | Current scope, portable startup, request status/retry protocol and Docker acceptance |
| [Backend reliability checkpoint](backend-verification.md) | Observed backend, browser, Docker and live A0 acceptance, preserved evidence and remaining boundaries |
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
| [繁體中文專案手冊](A-STELLAR_繁體中文專案手冊.md) | 專案架構、前後端啟動、設定、API、Docker 與測試導覽 |
| [A1–A6 資料集下載清單（繁中）](A1-A6_資料集下載清單_繁中.md) | 官方資料來源、下載指令、大小、儲存位置與科學使用限制 |
| [Frontend improvement TODO](FRONTEND_TODO.md) | English, prioritized frontend reliability, UX, accessibility, and test backlog |
| [Frontend TODO（繁中對照）](FRONTEND_TODO_繁中.md) | Frontend backlog 的繁中討論版；產品 UI 仍維持英文 |
| [P0 parallel implementation plan](P0_PARALLEL_IMPLEMENTATION_PLAN.md) | Sheng frontend and Sam backend workstreams, shared recovery contract, and joint acceptance |
| [P0 分工計畫（繁中）](P0_分工計畫_繁中.md) | Sheng/Sam 平行工作、同步節點與 P0 完成條件的繁中討論版 |
| [Quick and Advanced route planning contract](ADVANCED_ROUTE_PLANNING_CONTRACT.md) | Sheng/Sam P0 contract for simple planning, advanced parameters, and A0 chat context |
| [Journey Briefing ownership plan](JOURNEY_BRIEFING_OWNERSHIP_PLAN.md) | Sheng/Sam plan for grounded route briefing and future segment-level hazard evidence |
| [P1 mission assessment plan](P1_MISSION_ASSESSMENT_PLAN.md) | Canonical Sheng/Sam ownership, mission-profile, risk/confidence, map, and acceptance plan |
| [P1 token-weighted ownership plan](P1_TOKEN_WEIGHTED_OWNERSHIP_PLAN.md) | Remaining P1 work split 25% Sheng / 75% Sam by available implementation capacity |

Setup guides and overlapping agent reports are merged here. Scientific fixtures live in `data/fixtures/`; documentation contains no datasets. The repository-root README is the entry point.

Implemented API endpoints: `GET /api/v1/health`, `GET /api/v1/ready`, `GET /api/v1/regions`, `POST /api/v1/routes/plan`, `GET /api/v1/routes/{route_id}`, `GET /api/v1/a0/status`, `GET /api/v1/a0/capabilities`, and `GET/POST /api/v1/routes/{route_id}/chat`. Routing defaults to mock; explicit computed configuration enables validated terrain planning and durable retrieval. Live schemas are available at FastAPI's `/docs` and `/openapi.json`.

The `a0-*` documents preserve the approved scope and handoff. The implementation and API addendum are now exercised on a real CTX ROI; computed browser display remains pending alignment verification.
