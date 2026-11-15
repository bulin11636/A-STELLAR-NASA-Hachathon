# Backend demo acceptance checkpoint

Date: 2026-11-15 (UTC+08:00). Checkout: `A-STELLAR-NASA-Hachathon`.
Branch: `sam/backend`. This record describes observed tests, not a commit or push.

## Delivered behavior

- Chat records running, succeeded, failed and unknown request outcomes. Ordinary
  replay retrieves the original result or error without generating again.
- Versioned explicit retries respect eligibility, Retry-After and stale-version
  checks. Timeouts and abandoned workers retain an unknown outcome.
- Computed planning supports an optional Idempotency-Key. Existing plan/chat JSON
  bodies and successful response schemas remain unchanged.
- Status endpoints expose request outcomes through the
  [frontend handoff protocol](backend-handoff.md).
- The native launcher selects this checkout's paths and supports deterministic
  operation without provider requests.
- The Docker runtime includes the missing `libexpat1` dependency. Build-time
  Rasterio/PyProj imports detect shared-library failures before startup.
- Real-data Docker verification selects the advertised crater-scale example
  when available and verifies durable state after restart and recreation.
- The A0 acceptance harness covers planning, an explanation, adding three exact
  required points and reversing those visits, within four provider requests.
  Successful keyed plans and revisions are replayed without extra generation.

Frontend source and generated contracts were unchanged. The frontend owner keeps
presentation and map fitting; deferred features remain outside this delivery.

## Observed verification

| Check | Result |
| --- | --- |
| Backend suite | 309 passed, including competing workers, worker exit, retry versions/delays, legacy records and interrupted publication. |
| Frontend suite | 48 passed using the existing source. |
| Production frontend build | Passed. |
| Regional real DEM/API workflow | Passed: forward/reverse, other directions, terrain-weighted mode, independent native checks, eight-stop addition/reversal and fresh-service retrieval. Model mocked. |
| Production browser workflow | Passed: route/rationale, addition of two then six points, reversal, comparison, reload, focus/zoom/pan/expansion and regional display. Model mocked. |
| Synthetic Docker image/run | Passed: actual build, health, non-root runtime, read-only inputs, private-file access, missing configuration, persistent routes/chat/failures and idempotent replay after restart/recreation. |
| Real DEM Docker image/run | Passed the same checks with a 60,038.90 m regional route and 100 m search cells, validated against the 20 m native source. Source bytes unchanged. |
| Live A0 workflow | Passed with the configured `gpt-6.1-sol` provider: plan, explanation without revision, three-point addition, reversed visit order and fresh-app history/retrieval. Exactly four generation requests; no automatic retries. |
| Saved live results in production UI | Passed: actual model commentary, three-stop order, chat history, parent comparison and reload. All POST requests blocked during this display check; no additional generation. |

The first container attempt exposed the missing shared library; the corrected
image passed both fixture and real-source acceptance. Test containers, volumes
and unique image tags were removed by their isolated verifiers.

The real DEM SHA-256 remained
`ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`.
The regional API workflow also produced approximately 60.56 km, 65.10 km and
62.18 km routes in other directions/modes. These are projected research-route
lengths. Live language interpretation was tested on a smaller dynamic native
crop; regional terrain planning and Docker acceptance were verified separately.
The live UI check loaded saved responses rather than sending new chat messages.

## Local evidence

Machine-generated reports are ignored under `data/processed/`:

- Regional API: `regional-verification/run-20261115T000026Z-dca13878/summary.json`.
- Production browser: `ui-verification/run-2026-11-15T00-02-08-504Z/summary.json`.
- Synthetic Docker: `docker-verification/run-20261115T000322Z-a73217fec7cd/summary.json`.
- Regional Docker: `docker-verification/run-20261115T000553Z-15f4bb29f6ed/summary.json`.
- Live A0: `a0-workflow/run-20261115T000232Z-f8e09d7e/summary.json`.
- Saved live UI: `a0-workflow/run-20261115T000232Z-f8e09d7e/browser-display/summary.json`
  and `live-route.png`.

## Reproduce

Use the [regional guide](regional-verification.md) for offline API/browser checks.
From the repository root, with a working Docker engine:

```bash
python scripts/verify_docker.py --synthetic
python scripts/verify_docker.py --dataset-dir /absolute/path/to/dataset
```

These commands use deterministic mode and an empty private runtime file. They
remove only their unique project resources unless `--keep` is selected.

The A0 harness defaults to a mocked provider. Add `--live-model` only for an
explicitly requested real-provider acceptance run; the harness stops on failure
and caps this invocation at four new requests while retaining stricter configured
limits and the shared ledger:

```bash
python scripts/verify_agent_workflow.py --dataset-dir /absolute/path/to/dataset
```

To inspect this machine's saved live result without additional generation,
start this checkout with the saved run as its state directory:

```bash
python scripts/run_backend.py --dataset-dir /home/sam/nasa/project/dataset \
  --state-dir data/processed/a0-workflow/run-20261115T000232Z-f8e09d7e \
  --mode deterministic
```

Start the frontend separately, then open
`http://127.0.0.1:5173/?route=route-e02dbd2f0ffe4549a53aedea0009efe3`.
The saved commentary/history comes from the completed live run; the current
server is deliberately deterministic and will not perform new live chat revisions.

## Remaining boundaries

Recheck the final combined UI after the frontend owner's changes. NASA map/wire/
DEM registration remains unverified; browser tests blocked external NASA requests.
A usable DEM preview does not establish NASA overlay alignment. Thermal,
radiation and optical constraints remain unassessed, and contextual geology/
rover evidence is not fully fused into terrain costs. This is a research demo,
with deferred work listed in [TODO](TODO.md).
