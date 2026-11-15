# P0 frontend integration fixtures

These files are backend-owned, synthetic API examples. They contain no mission
measurements or live model output. Sheng can import them into frontend tests
without changing their wire shape.

| File | Meaning |
| --- | --- |
| `plan-running.json` | Active keyed plan; wait or poll. |
| `plan-succeeded.json` | Completed keyed plan; replay the original POST/key. |
| `plan-failed-retryable.json` | Known rejection; manual retry is eligible now. |
| `plan-failed-non-retryable.json` | Failed input; no execution under the same key. |
| `plan-unknown.json` | Uncertain provider outcome; never retry automatically. |
| `chat-failed-retryable.json` | Known chat rejection eligible for manual retry. |
| `chat-succeeded-revision.status.json` | Successful chat request status. |
| `chat-succeeded-revision.request.json` | Exact Advanced request for the revision. |
| `chat-succeeded-revision.json` | Full existing ChatResponse, including result and matching metadata. |
| `parent-route.json` | Persisted route discussed by that Advanced request. |
| `chat-request.schema.json` | Validation schema for old and Advanced chat requests. |

All status fixtures contain exactly the seven shared fields. `error` is null for
running/succeeded; failures contain `{code, message, details}` with nullable
`details`. The current backend sends integer `retry_after_seconds`, with zero
when no cooldown remains. It does not emit null for this field. `updated_at`
can be null for older records, although these new request fixtures have UTC
strings. Retry eligibility is false during a cooldown and for unknown outcomes.

The paired revision changes the objective from shortest to safest while keeping
Start and Goal. Its parent ID is `route-00000000000000000000000000000000`; its
child ID is `route-11111111111111111111111111111111`. IDs and timestamps are
normalized for stable examples. Artifact references are illustrative; do not
install these records in the runtime store or treat fixture hashes as real-data
provenance.

Regenerate from the repository root:

```bash
python scripts/export_p0_fixtures.py
```

The exporter uses a synthetic Mars DEM, the real API and a mocked provider. It
never reads a credential for provider execution and never makes a live model
request. Backend tests validate schemas, parent/context relationships, status
semantics and regeneration. The seven status fixtures also pass Sheng's existing
TypeScript decoder.
