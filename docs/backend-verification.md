# Backend reliability checkpoint

Date: 2026-11-15 (UTC+08:00). Checkout: `A-STELLAR-NASA-Hachathon`.
Branch: `sam/backend`. Existing diagnostics from `main` were fast-forwarded onto
the branch before this work. This checkpoint does not imply a new commit or push.

## Delivered behavior

- Chat stores running, succeeded, failed and unknown request outcomes. Ordinary
  replay retrieves the original result or recorded error without generating again.
- Explicit versioned retries are permitted only for eligible known rejections.
  Retry-After and stale-version checks prevent early or duplicate retries.
- Timeouts, abandoned workers and legacy claims without a response remain unknown.
  A completed response remains recoverable after an interrupted final status write.
- Computed planning accepts an optional Idempotency-Key. Existing unkeyed planning
  and existing plan/chat JSON bodies and success schemas remain unchanged.
- Additional status endpoints expose outcome and retry eligibility. The frontend
  owner can integrate these through the [handoff protocol](backend-handoff.md).
- The native launcher selects this checkout's paths, validates local readiness and
  supports deterministic operation without provider requests.
- Docker acceptance and CI commands use isolated state, an empty private runtime
  file and deterministic routing. The prepared workflow checks actual image health,
  built assets, non-root execution, read-only inputs, missing configuration, and
  persistence after both restart and container recreation.

Frontend source and generated frontend contracts were not changed. Deferred
features remain listed in the handoff and TODO; the scientific planning scope
remains research terrain routing.

## Observed verification

| Check | Result |
| --- | --- |
| Backend suite | 309 passed. Includes competing workers, real worker exit, retry versions/delays, legacy records, interrupted publication and corrupt-response protection. |
| Frontend suite | 48 passed using the existing source. |
| Production frontend build | Passed. |
| Native launcher against the real DEM | Local planning, state-directory permissions and mode checks passed in deterministic mode. No provider access was asserted. |
| Regional real DEM/API workflow | Passed: forward/reverse and other-direction requests, terrain-weighted mode, native segment checks, eight-stop addition/reversal and fresh-service retrieval. |
| Production browser workflow | Passed: route/rationale, incremental addition of two then six points, reversal, comparison, reload recovery, focus/zoom/pan/expansion, and regional display. |
| Docker fixture/command preparation | Passed with the synthetic fixture. |
| Actual Docker image/run | Blocked at the WSL CLI/integration prerequisite. No image was built by that run. |
| Live-model generation | Not run in this checkpoint. Model responses in verification were mocked. |

The real-source workflow retained the source hash and produced approximately
60.04 km, 60.56 km, 65.10 km and 62.18 km routes in its selected directions/modes.
These are projected research-route lengths. The browser test blocked external
NASA requests; it does not establish NASA map registration.

Ignored local evidence under `data/processed/`:

- Regional: `regional-verification/run-20261114T190932Z-1b2ea6cc/summary.json`.
- Browser: `ui-verification/run-2026-11-14T19-16-00-930Z/summary.json`.
- Docker preparation: `docker-verification/run-20261114T185518Z-98215a4ca125/summary.json`.
- Docker prerequisite check: `docker-verification/run-20261114T193213Z-2448719db72e/summary.json` and its `docker.log`.

## Remaining acceptance

Enable Docker Desktop's WSL 2 integration, verify that `docker version` reports
both Client and Server, and run:

```bash
python scripts/verify_docker.py --synthetic
python scripts/verify_docker.py --dataset-dir /absolute/path/to/dataset
```

Only a `passed` image run establishes container acceptance. A prepared fixture,
local HTTP pass or configured future CI job is not a substitute. The verifier
removes only its own uniquely named project/volume unless `--keep` is selected.

Live-model acceptance remains a separate controlled test with an available test
account. Frontend retry controls, scientific evidence fusion, further terrain
refinement, backup/restore and other deferred items remain pending as documented.
