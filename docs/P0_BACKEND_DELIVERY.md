# Sam P0 backend delivery

Date: 2026-11-15 (UTC+08:00). Branch: `sam/backend`, fast-forwarded to the merged
`main` baseline before implementation. No frontend source was changed.

This completes Sam's backend responsibilities in the
[P0 ownership plan](P0_PARALLEL_IMPLEMENTATION_PLAN.md) and
[Advanced planning contract](ADVANCED_ROUTE_PLANNING_CONTRACT.md). It does not
claim that Sheng's remaining UI work or the joint P0 product acceptance is done.

## Delivered contract

| Area | Behavior |
| --- | --- |
| Recovery | Both status endpoints retain the same seven fields and no-store responses. |
| Identity | Computed plans bind their key to the body. Chat binds request_id to message plus the entire optional Advanced context. |
| Persistence | Success replays without execution; failed/unknown states remain available after restart. Old chat bodies and successful records without input sidecars remain supported. |
| Retry | Only a known eligible failure and the current attempt version can execute. Cooldown failures include Retry-After. Unknown outcomes cannot execute again under the same key. |
| Advanced validation | Literal schema/interface versions, objective enum, 0–16 finite ordered waypoints, 1–3 unique focus values, strict revision boolean and no unknown fields. |
| Parent binding | Objective and ordered required waypoints must exactly match the persisted parent. A mismatch returns HTTP 422 / ADVANCED_CONTEXT_MISMATCH before generation and is durably recorded. |
| Revision policy | A false allow_supported_revision is enforced by Python even if model output proposes a revision. The response has null result/metadata and explicitly says the route is unchanged. |
| Context | Validated Advanced input is stored privately and supplied to A0 in typed form. The existing trimmed 1–1,600 character message remains the only free-text requirement. |
| Runtime | Readiness reports planning/dataset configuration, storage and credential checks separately. Storage covers writable state paths and the local usage ledger's integrity. |
| Provider status | Credentials and recorded transport outcomes are distinguished from current availability. Readiness/status never make a provider request. |
| Errors | Existing JSON envelope retained, including stored validation details. Unexpected failures log only their exception class; raw exception/provider text, paths and credentials are not exposed. |

The model input includes one authoritative Advanced waypoint list rather than
repeating it inside the parent request. All 16 required stops can be explained
within the existing context guard; limits and reservation policy were not raised.
Analysis focus supplies explanation context, not a terrain-cost override or a
new scientific constraint. An oversized combined context still receives HTTP 413
before generation; shortening its input requires a new intended request/ID. Backend rationale describes a terrain computation
without claiming route certification or global optimality.

## Sheng handoff

The [shared fixture directory](../data/fixtures/p0/README.md) contains the five
plan states, retryable chat failure, successful chat status, complete revision,
matching parent, Advanced request and input schema. Existing success responses
are unchanged. The optional Advanced request is also exposed by OpenAPI at
`/docs` and `/openapi.json`.

For new chat requests the complete typed input is stored as
`requests/chat/<route_id>/<request_id>.input` under the configured route store.
It is private application state, not a new response field. Keep that directory
with responses when retaining state. Do not alter the context on a retry;
changed focus, permission or waypoints require a new intended request/ID.

Status specifics retained for the existing browser client:

- `retry_after_seconds` is a nonnegative integer; zero means no cooldown remains.
- `updated_at` may be null for a legacy record.
- `retry_allowed` is false while waiting and for every unknown outcome.
- No record returns a JSON 404 error, not a fabricated unknown status.
- Malformed request IDs and headers return the existing JSON 422 error.
- The legacy mock planning endpoint does not support keyed persistent plans;
  supplying a key there returns a JSON 400 error.

Runtime additions are additive:

- `/ready`: checks are `planning`, `storage`, `model_credentials`; the endpoint
  returns 503 when a local requirement fails. `provider_access_verified` is false.
- `/a0/status`: existing mode/model/configured/limits are retained; checks,
  usage_available and provider_access_verified are explicit. Budget is null when
  disabled or unavailable. A storage problem does not fabricate usage numbers.
- `provider.availability` is `disabled` or `not_checked`.
  `last_request_outcome` is `not_requested`, `response_received`, `rejected` or
  `unknown`; `last_http_status` is a recorded rejection status or null.
- `last_provider_error` is the most recent retained allowlisted diagnostic,
  including historical failures; it does not certify the latest request failed
  or predict whether the provider is available now.

## Verification

Run from `backend/`:

```bash
python -m pytest -q
```

New coverage includes Advanced validation, parent mismatch, persisted context,
permission enforcement against contrary model proposals, all 16 stops, explicit
retry/restart, competing workers, unknown outcomes, corrupt input, shared fixture
contracts, storage failures, ledger integrity and passive provider observations.

Run from the repository root:

```bash
python scripts/export_p0_fixtures.py
python scripts/verify_docker.py --synthetic
python scripts/verify_docker.py --dataset-dir /absolute/path/to/dataset
```

The image test now sends an Advanced explanation-only chat request and replays it
after both process restart and container recreation. All tests in this delivery
use deterministic routing or mocked model responses. No live generation was
performed. Earlier live acceptance is recorded separately in the
[demo checkpoint](backend-verification.md).

Observed results:

| Check | Result |
| --- | --- |
| Backend suite | 358 passed, including all new Advanced/recovery/runtime/fixture checks. |
| Existing frontend suite | 51 passed; frontend source unchanged. |
| Production frontend build | Passed. |
| Shared status fixtures | All seven passed Sheng's existing TypeScript decoder. |
| Native real-DEM readiness | Passed; planning, storage and credentials checks remained separate, with no provider probe. |
| Production browser regression | Passed: eight-stop additions/reversal, rationale, parent comparison, reload recovery and crater-scale display. Model mocked. |
| Synthetic Docker integration | Passed actual build/run, Advanced chat and restart/recreation persistence. |
| Final real-DEM Docker integration | Passed with a 60,038.90 m regional route, 100 m search cells, native-source checks, Advanced chat persistence and immutable source bytes. |

Ignored local evidence under `data/processed/`:

- Browser: `ui-verification/run-2026-11-15T02-08-24-636Z/summary.json`.
- Synthetic Docker: `docker-verification/run-20261115T020645Z-ea62d6e4b050/summary.json`.
- Final real-DEM Docker: `docker-verification/run-20261115T021723Z-62fc081ff9e6/summary.json`.

Docker test resources were removed after their checks. The real DEM retained
SHA-256 `ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`.
The browser regression covers the current UI, not Sheng's future Advanced UI.
Model interpretation in new P0 tests is mocked; no new live-model acceptance is
claimed.

## Remaining joint work

Sheng owns Quick/Advanced controls, waypoint interaction and lifecycle UI. After
those changes merge, run the joint UI acceptance matrix. Computed geometry must
remain off the NASA basemap until independent registration is established.
No safety certification, new evidence fusion, automatic stop optimization or
new model adapters are included in Sam's P0 delivery.
