# Policy and assessment fixtures

These fixtures are generated with `python scripts/export_p1_fixtures.py` through
the actual synthetic terrain planner and assessment pipeline. No live model,
NASA field observation, or medical safety certification is represented.

| File family | Intended use |
| --- | --- |
| `policies.json` | Typed profile selector and bounded resolution catalog |
| `profile-*-*.json` | Four profiles × three resolutions, durable policy/leg/assessment metadata |
| `missing-radiation.json` | Required weighted factor missing: null risk and explicit confidence/reason |
| `blocked-scenario.json` | Required scenario budget failure: blocked, no comparable risk |
| `required-thermal-unassessed.json` | User-required uncalibrated thermal analysis remains unassessed |
| `low-risk-low-confidence.json` | Small relative score with insufficient evidence confidence; no safety claim |
| `unverified-alignment.json` | Unverified registration; a demo overlay is not evidence of alignment |
| `verified-alignment-synthetic.json` | Synthetic registration-verifier fixture, never production alignment proof |

Risk and confidence are paired percentages under `metadata.assessment`.
Per-factor risks remain normalized 0..1; weighted contributions use 0..100.
The legacy `result.metrics.risk_score` remains null. Use the supplied English
reasons and evidence states, and join internal specialist IDs to their full
public names in worker/trace metadata. A5 remains explicit `not_applicable`.

Only route IDs, timestamps, elapsed timings and private-file artifact digests are
normalized for deterministic export. Source hashes, route geometry, distances,
policy bounds and computed assessment/control values are retained. Reproduction
is tested byte-for-byte. Fixture JSON does not include its private route artifacts
and cannot be inserted into a production route store as a published run.

See [architecture](../../../docs/architecture.md#assessment-semantics) for
assessment semantics, [API contracts](../../../docs/api.md) for stored values,
and [map registration](../../../docs/map-registration.md) for independent controls.
