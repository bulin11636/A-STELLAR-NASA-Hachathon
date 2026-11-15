# Backend handoff prompt

Use this prompt in a new chat with this repository open.

```text
Work in ~/nasa/repo/A-STELLAR-NASA-Hachathon on sam/backend.
Inspect repository instructions and git status first. Preserve existing changes.
Read docs/SPECIALIST_ROUTING_AND_WALKING.md, docs/P0_UI_ACCEPTANCE.md, docs/P0_BACKEND_DELIVERY.md, docs/backend-handoff.md, docs/TODO.md,
docs/ADVANCED_ROUTE_PLANNING_CONTRACT.md and docs/docker.md. Repository documentation must be English.
Keep TODO limited to pending work; do not record personal usage or billing.

The current scope is reliable delivery of the existing prototype. Retain
regional terrain A*, up to 16 ordered waypoints, chat additions/reordering,
persisted rationale, immutable routes, source validation and provider diagnostics.
UI styling and map fitting belong to the frontend owner; keep frontend source
stable except for the coordinated optional mission, assessment and specialist-trace
contract extension documented in the specialist integration guide. Preserve walking-only
assumptions, required-analysis enforcement, metered two-stage selection and its
durable retry checkpoints. Do not introduce calibrated risk values without data. Sam's P0 work is complete;
chat additionally accepts the optional typed advanced_context. Preserve its
parent-route matching, context-bound request identity and host-enforced
explanation-only permission. The joint P0 UI fixes are also complete; use the latest acceptance report
before treating historical gap reports as pending work.

Backend recovery uses durable request states and explicit, versioned retries.
Known failed requests replay their saved error unless explicitly retried;
timeouts/worker exits remain unknown and are never automatically re-executed.
Planning supports optional Idempotency-Key. Read the backend handoff for the
new status endpoints and X-A-Stellar-Retry-Attempt header before changing them.

Use scripts/run_backend.py for portable native startup and local-only checks.
Use scripts/verify_docker.py --synthetic for isolated real-image acceptance,
and --dataset-dir with the external DEM directory for real-source acceptance.
A prepare-only run is not an image test. Keep source mounts read-only and retain
route/chat/request state across normal restarts. Tests must not use real keys
or live generation by default. Never print or commit .env contents.

Defer avoidance areas, automatic itinerary ordering, optional stops, long-term
memory, new progress/cancellation jobs, extra models/DEMs and calibrated thermal
or radiation fusion. Keep unassessed evidence explicit. Coordinate adapter math
alone does not establish NASA map registration.

Run relevant backend and integration checks. Keep API/provider and actual Docker
acceptance separate from mocked/local verification. Do not make paid generation
requests to diagnose an unresolved provider rejection. Do not commit or push
unless the current user authorizes that action. Report changes, validation,
remaining blockers and commands the user can reproduce.
```
