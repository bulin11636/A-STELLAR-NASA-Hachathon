# P0 UI fixes and local walkthrough

Date: 2026-11-15 (UTC+08:00). Originally implemented on `sam/backend` from
`87238e3`, then integrated onto `main` after upstream `5668574`. The user authorized completing both frontend and integration fixes.
This supersedes the open findings in the [integration gap report](P0_INTEGRATION_GAPS.md).

## Delivered behavior

- Each new plan gets a new idempotency key. A pending action retains its original
  input, key and context for explicit retry/recovery.
- Draft coordinates, objective and Advanced preferences are separate from the
  last successful result. Edits and subsequent failures keep that result visible;
  Clear selections explicitly removes it.
- Quick submits only Start, Goal and objective. Hidden Advanced stops do not
  influence Quick. Advanced provides coordinate/map waypoint creation, ordered
  W1/W2 markers, reorder/removal, focus, revision permission and bounded requirements.
- Plan and Ask A0 submits the base plan, retrieves and matches persisted metadata,
  then sends exactly one chat request with that parent route's typed context.
  Failure before metadata verification never sends chat. A chat failure preserves
  the base route.
- Plan and chat expose running/succeeded/failed/unknown states. Retry is manual,
  uses the original body and current attempt version, and is unavailable during
  cooldown or for unknown/non-retryable outcomes. Status polling is GET-only.
- Pending actions survive page reload in session storage. Restoring state never
  generates. A known successful result can be explicitly recovered with the
  recorded ID/version; the server replays its stored response.
- Chat identity includes Advanced context. Context for discussing a displayed
  route comes from its metadata, even while the user edits the next draft.
  Late plan, metadata, status and chat responses cannot replace newer selections.
- Informational replies explicitly say the route did not change. A paired,
  matching revision alone replaces the result. Explanation-only context cannot
  accept a contrary revision response.
- Runtime labels separate routing mode, dataset/profile, storage, credential
  presence and recorded provider transport outcomes. Configuration is not a
  claim of current provider access. Consecutive duplicate stops are rejected
  before network submission.
- Computed route geometry remains on the DEM preview. Draft W markers do not
  enable computed lines on the unverified NASA basemap.

## Start the application with Docker

Use the current working checkout. Docker Desktop must be running with WSL
integration enabled. No host Node installation is needed for this option.
From WSL:

```bash
conda activate nasa
cd ~/nasa/repo/A-STELLAR-NASA-Hachathon
python scripts/run_docker.py \
  --env-file "$PWD/.env" \
  --dataset-dir "$HOME/nasa/project/dataset" \
  --mode agentic
```

Open **http://127.0.0.1:8080**. The image serves the UI and API on the same origin.
The supplied private runtime file and DEM directory are mounted read-only;
application state persists in the project volume. The launcher builds the current
source, including these fixes. It does not start a model request by itself.
User planning/chat actions in agentic mode can call the provider.

To exercise terrain planning without live model calls, use the same command with
`--mode deterministic`. In that mode, chat explains existing terrain results;
use Advanced's waypoint editor to change the next plan. Natural-language model
revisions require agentic mode and working provider access.

For port conflicts, add `--port 8081` and open that port. Inspect logs with the
same arguments plus `--action logs`. To stop while retaining saved state:

```bash
python scripts/run_docker.py \
  --env-file "$PWD/.env" \
  --dataset-dir "$HOME/nasa/project/dataset" \
  --action down
```

## Manual walkthrough

1. In Quick, select **Load in-coverage example endpoints**, then **Plan Route**.
   Inspect the DEM preview and Planning rationale. Try **Load crater-scale
   example endpoints** and plan again without reloading; this must create a
   separate request and show the regional result.
2. Select Advanced and reload the in-coverage endpoints. Add the two coordinates
   below using **Waypoint longitude**, **Waypoint latitude**, **Add waypoint**.
   Their availability was checked against the selected native CTX grid; they are
   demo inputs, not NASA imagery registration controls.

   | Stop | Longitude | Latitude |
   | --- | --- | --- |
   | W1 | 77.43871828425854 | 18.456610420826674 |
   | W2 | 77.45294742485665 | 18.443113936940183 |

3. Choose terrain focus, disable **Allow A0 to propose a supported route revision**
   for an explanation-only test, and enter:

   ```text
   Explain the terrain limitations and why this route follows the required waypoint order.
   ```

   Select **Plan and Ask A0**. The base route appears before the A0 answer. The
   answer should be informational and leave the route unchanged.
4. Enable supported revisions. In **Message A0**, enter:

   ```text
   Reverse all required waypoint visits, keeping the same start, goal and shortest objective.
   ```

   A supported revision appears as a new route with parent comparison. Use
   **Focus W1**, **Fit route** and zoom/pan to inspect nearby stops. Reload and
   confirm that the route and chat history return.
5. To test an additional point, send:

   ```text
   Add 77.4458328545576,18.44986217888343 after the existing required stops. Keep the start, goal and shortest objective unchanged.
   ```

   This extra coordinate was also checked against the native planning grid.
   The previous route remains available if the request fails.
6. If a request fails, read its recorded state. Use **Retry planning request**,
   **Retry chat request**, or the Advanced A0 recovery control only when offered.
   An unknown outcome offers status checking, not automatic resubmission.

## Verification boundaries

All automated model responses in this delivery are mocked. No new live-provider
generation is claimed; the user's manual agentic workflow above is the real
provider exercise. NASA imagery requests were blocked during browser tests.
Neither the preview nor these tests certify NASA registration or route safety.
Scientific evidence fusion and the other deferred items remain outside P0.

Reproduce the focused acceptance from the repository root after building the UI:

```bash
node scripts/audit_p0_ui.mjs --dataset-dir /absolute/path/to/dataset --python /path/to/python
```

The dedicated acceptance server has bounded provider scenarios under __test;
those exist only in scripts/ui_test_server.py and are not part of the production
application or Docker image. No user API key is used by that server.

## Observed results

| Check | Result |
| --- | --- |
| Backend regression | 358 passed. |
| Frontend tests | 72 passed. |
| Production build | Passed. |
| Focused P0 browser acceptance | 26 checks passed, including actual backend retry records, lost-response recovery with no extra generation, unknown/running outcomes and backend restart. |
| Existing browser regression | Passed: eight-stop addition/reversal, parent comparison, reload, focus/zoom/pan/expansion and regional planning. |
| Final Docker image | Real DEM build/start, UI/API, read-only mounts, health, Advanced chat persistence, restart and recreation passed. Regional route: 60,038.90 m. |
| Live model requests | Zero in this delivery. |

Ignored local evidence under data/processed:

- P0 UI: `p0-ui-audit/run-2026-11-15T04-36-25-369Z/summary.json`.
- Legacy browser: `ui-verification/run-2026-11-15T04-27-15-108Z/summary.json`.
- Final Docker: `docker-verification/run-20261115T043439Z-e4ef898a21a6/summary.json`.

The P0 audit retains regional-route.png, advanced-stops.png and
unknown-recovered.png. All acceptance processes and uniquely named Docker test
resources were cleaned up. The normal application has not been left running;
use the startup command above. Changes remain in the working tree for manual
commit/push.
