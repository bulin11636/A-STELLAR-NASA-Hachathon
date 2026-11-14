# A0 expanded ROI and chat: delivery checkpoint

Historical checkpoint. See [regional verification](regional-verification.md)
and [Docker runtime](docker.md) for the subsequent implementation and acceptance.

Date: 2026-11-14. Branch: `team/a1-a2-sheng-integration`.
Base commit: `4b80f83`. Changes are left uncommitted for the user.

## Delivered behavior

- Computed Plan Route enters the metered A0 adapter when agentic mode is enabled,
  then delegates to the existing deterministic A*/validator/store. Model default:
  `gpt-6.1-sol`, medium reasoning, Standard processing, no automatic paid retries.
- Backend-only root `.env` loading with process-variable precedence and an
  optional external `A_STELLAR_ENV_FILE`; no credential values were printed or
  committed. The placeholder `.env.example` documents the supported settings.
- Dynamic native-resolution cropping for endpoints and up to six ordered
  waypoints outside the original seed window. The example profile allows one
  million cells, 500,000 search expansions and a shared 15-second search budget.
- Plan explanations, actual model usage and parent-linked route revisions are
  persisted with route metadata. Worker results are preserved in private
  provenance; only compact facts and selected source POIs enter model context.
- The UI includes an ordered coordinate editor, a dedicated rationale section,
  route-scoped chat, API usage status and an independent DEM-axis route preview.
  The URL carries the current route ID so reload restores metadata and history.
- Questions do not change a route. Explicit supported mode/waypoint changes
  create a new validated route, preserving the old one. Duplicate message IDs
  do not trigger another paid request; the UI retains the ID after a failed send.
- The newer frontend source at `origin/sheng/frontend-mock-integration`
  (`b22a9f0`) was reconciled, including layers, point evidence and mission briefing.
  Both sets of MarsMap imports and local planning controls were retained. No
  merge commit was created; source integration is in the working tree.
- The two previously failing metadata audit probes now pass. Persisted grid
  shape, positive resolution, affine, CRS and source-window consistency are checked.

## Actual checks

| Check | Result |
| --- | --- |
| Full backend suite | **258 passed**; existing Affine warnings remain. |
| Full frontend suite | **41 passed**; renderer deprecation notices remain. |
| Frontend production build | Passed; existing >500 kB bundle warning remains. |
| Original independent metadata probes | **2 passed**, previously both failing. |
| Real DEM, mocked A0, full plan/question/waypoint-revision flow | Passed; crop expanded from 128x128 to 229x229, fresh app restored route/chat. |
| Deterministic real HTTP/process-restart verifier | Passed for both planning modes; it explicitly disables model calls. |
| Chromium end-to-end UI | Passed with real DEM/API and mocked model; external NASA requests were explicitly blocked. |
| Real GPT-6.1 Sol API | **Not passed: first request returned HTTP 429; stopped without retry.** |

Final regression commands:

```bash
# backend/
/home/sam/miniconda3/envs/nasa/bin/python -m pytest -q --disable-warnings
/home/sam/miniconda3/envs/nasa/bin/python -m pytest -q ../data/processed/a0-audit/20261114T064321Z/test_persistence_acceptance.py

# frontend/
PATH=/tmp/node-v22.23.5-linux-x64/bin:$PATH npm test
PATH=/tmp/node-v22.23.5-linux-x64/bin:$PATH npm run build

# repository root; real DEM, synthetic model responses, no paid calls
/home/sam/miniconda3/envs/nasa/bin/python scripts/verify_agent_workflow.py
```

The old independent test path is local ignored evidence. Its two findings also
have portable regression coverage in `backend/tests/test_route_agent.py`.

Local artifacts:

- Final mocked workflow:
  `data/processed/a0-workflow/run-20261114T092459Z-eaad28d8/summary.json`.
- Live attempt:
  `data/processed/a0-workflow/run-20261114T090053Z-f0e54a11/summary.json`.
- Deterministic HTTP/restart:
  `data/processed/a0-verification/run-20261114T090631Z-cfafc5da/summary.json`.
- Chromium UI run:
  `data/processed/a0-browser/run-2026-11-14T09-13-50-885Z/summary.json`
  and `ui.png` in that directory.

The browser exercised example planning, the rationale/preview, a question,
chat-driven mode revision, reload restoration, manual ordered waypoints and a
229x229 dynamic crop. Four external requests were blocked and there were no
browser page errors. Temporary Playwright/Chromium tooling was installed under
`/tmp`, not added to project dependencies. The browser run preceded the final
private-provenance/accounting refinements; those passed final regression and
the final real-DEM mocked workflow. Browser results are not live-model or NASA
registration verification.

## Model cost and current external blocker

A real provider verification attempt returned HTTP 429 and stopped without
automatic retry. The cause was not established as a rate limit versus provider
account availability. The implementation recognizes an explicit
`insufficient_quota` response when supplied; that branch has mocked tests.
Successful live-model behavior remains unverified. Mocked provider tests are
not evidence of a successful live-model call.

To inspect the UI now without more paid requests, start the backend with:

```bash
export A_STELLAR_A0_MODE=deterministic
```

Use the rest of the computed-mode startup commands in the
[agent/chat guide](a0-agent-chat.md). Manual waypoint planning, preview and
stored explanations work. Deterministic chat explains the stored result and
directs edits to the coordinate editor; it does not pretend to perform live
natural-language replanning. Return to `agentic` mode only when ready to test
the configured API account again.

## Resume development

1. Read this checkpoint and inspect git status; preserve the uncommitted work.
   Do not rebuild features from the earlier deterministic-only prompt.
2. Resolve the external API 429 before another live attempt and retain the
   configured application safeguards.
3. If runtime code changes, run focused checks first and required combined
   regression after fixes.
4. Remaining product work includes independent NASA map/wire/DEM registration,
   calibrated A2/A3 constraints, richer place/avoidance preferences, larger or
   multi-resolution corridors, Docker packaging and manual Git history integration.
5. Keep the completed source available for the user's manual commit. No commit,
   push, live browser/NASA registration claim or Docker release was performed.
