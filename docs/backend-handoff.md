# Backend delivery and frontend integration

Work in `A-STELLAR-NASA-Hachathon` on `sam/backend`. Frontend presentation and
map fitting remain with the frontend owner. Existing plan bodies and successful
plan/chat response schemas are unchanged. Chat accepts optional Advanced context. This scope improves request recovery
and deployment verification without adding itinerary optimization or new mission
constraints.

See the [reliability checkpoint](backend-verification.md) for observed results;
the commands below describe how to reproduce acceptance, not a claim that all
external prerequisites have already been satisfied.

Advanced context and current P0 status details are in the [Sam P0 delivery](P0_BACKEND_DELIVERY.md); shared examples are in [P0 fixtures](../data/fixtures/p0/README.md).

## Start this checkout

From the repository root, in a Python environment with `planning,agentic` extras:

```bash
python scripts/run_backend.py --dataset-dir /absolute/path/to/dataset --mode deterministic --check
python scripts/run_backend.py --dataset-dir /absolute/path/to/dataset --mode deterministic
```

Use `--mode agentic` when provider access is available. `--env-file` selects an
external private runtime file; otherwise this checkout's `.env` is selected when
present. Credentials are read as data and never printed. `--state-dir` selects
the persistent processed-state root. Its default is this checkout's
`data/processed`, preserving state across ordinary restarts. The launcher does
not copy state from another checkout; select an existing state root explicitly
when needed. Public path/mode overrides take precedence over file settings.

`--check` probes the local DEM/profile and state-directory permissions without
starting a server or contacting the provider. It does not establish available
provider credits or generation access.

The native launcher serves the API on port 8000. Start the frontend separately
with `npm run dev -- --force` in `frontend/` and open the Vite URL, normally
`http://127.0.0.1:5173`. The API health URL is
`http://127.0.0.1:8000/api/v1/health`; its root path is not the development UI.
Stop the earlier checkout's backend before reusing port 8000. Vite's existing
development proxy still targets that port.

## Request recovery protocol

Chat retains `{message, request_id}` and additionally accepts optional `advanced_context` under the agreed Advanced contract. Planning optionally
accepts `Idempotency-Key` in computed mode. Keys use 16–64 ASCII letters, digits,
underscores or hyphens. Generate a key once for an intended action and retain it
while its outcome is unresolved. A different input needs a different key.
Unkeyed planning retains its previous behavior and is not deduplicated.

Status endpoints:

- `GET /api/v1/routes/requests/{request_id}` for a keyed plan.
- `GET /api/v1/routes/{route_id}/chat/attempts/{request_id}` for a chat message.

Each returns `request_id`, `state`, `attempt`, `retry_allowed`,
`retry_after_seconds`, nullable `error`, and nullable `updated_at`.

| State | Client behavior |
| --- | --- |
| `running` | Wait or query status. Do not submit a new model request. |
| `succeeded` | Replay the original POST with the same body/key to retrieve its original response. |
| `failed` | Show the recorded failure. An ordinary replay repeats that error without another model call. |
| `unknown` | The worker ended, timed out or returned an uncertain outcome. Automatic execution and same-key retries remain blocked. |

For a failed attempt with `retry_allowed: true`, a deliberate user action may
repeat the original POST with `X-A-Stellar-Retry-Attempt: <attempt>`. Retain the
same message/body and request ID or plan key. The attempt number must match the
current failed version. A delayed duplicate cannot start another retry after
that version has advanced. Honor `retry_after_seconds`; early retries receive
HTTP 429 without contacting the provider.

Known provider rejections and local pre-send configuration/budget failures can
be eligible. Timeouts, uncertain server outcomes and already-consumed invalid
model outputs are not automatically replayable. Existing reservations and
application limits remain in force; this feature does not reset counters.

Failures also carry attempt metadata in the existing error `details` list.
Its values remain strings, preserving the current ErrorEnvelope contract.
The UI can use the status endpoints directly if its error wrapper does not
retain details. Only show a retry control for a known eligible attempt, and
never add an automatic model retry loop.

Legacy successful chat records still replay and appear in history. Old `.claim`
files without a response have no reliable outcome and appear as `unknown`.
They are never cleared by age. A per-key SQLite transaction supplies active
process locking; request state and responses use atomic filesystem publication.
Published responses remain replayable if the final status update was interrupted.
Unrelated keys can execute concurrently.

## Verification

Run `python -m pytest -q` from `backend/`. The recovery checks cover rejected
requests, explicit retry versions, Retry-After, competing workers, worker exit,
restart retrieval and keyed planning without real provider requests.

With Docker Desktop's WSL 2 engine/integration enabled:

```bash
python scripts/verify_docker.py --synthetic
python scripts/verify_docker.py --dataset-dir /absolute/path/to/dataset
```

These commands build the real image and use a private empty env file in
deterministic mode. They inspect read-only mounts and non-root execution,
exercise missing configuration, plan a route, send a chat message, restart and
recreate the container, and verify route/history/failure/idempotency persistence. Source bytes
must remain unchanged. Each run uses a unique Compose project/volume and removes
only its own resources. Reports remain in ignored
`data/processed/docker-verification`. `--keep` retains test resources for inspection;
`--prepare-only` validates fixtures/commands but does not constitute image acceptance.

CI runs the synthetic Docker workflow and preserves its summary/log artifact.
Real-source acceptance additionally requires local DEM inputs. Successful local
HTTP tests or a prepared fixture do not establish a successful Docker image run.

## Scope kept for this delivery

Retain regional terrain A*, ordered waypoint editing/revisions, grounded rationale,
durable routes/chat and provider diagnostics. The selected live-model workflow
and Docker acceptance have passed; see the [checkpoint](backend-verification.md)
for test boundaries and evidence. Repeat live checks only when explicitly requested.

This delivery demonstrates the core workflow rather than production readiness.
Acceptance means a user can plan a regional route, inspect its geometry and
rationale, explicitly add or reorder stops through chat, and retrieve saved
results after a restart. Show whether a result uses the live agent or deterministic
mode. Mock-provider tests do not establish live-agent acceptance. Verify the Docker
image before describing the packaged deployment as tested.

The frontend owner handles map fitting, zoom and presentation. A usable DEM view
can support the demo while NASA registration remains explicitly unverified;
display adjustments must not change that status. A1 terrain currently affects
planning costs; contextual A4/A6 evidence and unassessed A2/A3 inputs must not be
presented as fully fused mission constraints.

Until this acceptance sequence passes, prioritize failures that block it and
integration fixes. The deferred tasks in [TODO](TODO.md) are future exploration,
not requirements for this demo. Advanced retry controls, operational backup/restore
and general-purpose model support do not expand this delivery's acceptance scope.

Deferred: avoidance geometry, optional visits, automatic stop-order optimization,
long conversation summaries, progress/cancellation jobs, additional model adapters,
additional DEMs, narrow-passage refinement, and calibrated thermal/radiation cost
fusion. Keep unsupported constraints explicitly unassessed.
