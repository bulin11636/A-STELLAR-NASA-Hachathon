# A0 integration with the current frontend

Status: integration handoff and observed source inventory, not a test report.
Remote refs were fetched on 2026-11-14. Recheck them before implementation;
this snapshot must not freeze later development to these commits.

Read this alongside the [A0 plan](a0-implementation-plan.md),
[API addendum](a0-api-contract.md) and [verification guide](a0-verification.md).

## Observed remote and local state

| Source | Observed revision/state | Implication |
| --- | --- | --- |
| Local integration branch HEAD | `a105e51` | Committed evidence-loop baseline; not the complete working tree. |
| `origin/team/a1-a2-sheng-integration` | `4b78b6a` | One newer commit, `Add verified data acquisition handoff`. |
| `origin/sheng/frontend-mock-integration` | `4b78b6a` | The frontend-named branch currently points to the same commit as the remote integration branch. |
| Remote frontend diff from local HEAD | No changes under `frontend/` between `a105e51` and `4b78b6a` | The newly fetched commit does not itself introduce additional frontend source changes. The existing F1.5 frontend remains the integration baseline. |
| Local working tree | The user paused partially completed backend/frontend implementation when remote updates appeared | Preserve and resume these modified/untracked files after reconciliation; they are neither a validated release nor an empty starting point. |

The user confirmed that local development is paused. The handoff is therefore
to reconcile remote updates with a stable unfinished implementation, then
continue from it. Do not assume another chat is still writing these files
unless a subsequent inspection or user update establishes that situation.

The remote commit adds a verified acquisition manifest, downloader, source
documentation, ignore rule and a Python 3.10 setup clarification. In particular,
the manifest records a CTX radius discrepancy between the raster and provider
summary and identifies the daytime THEMIS mosaic as prototype visual data.
Review those records before choosing source/CRS policy; do not infer valid
geometry or calibrated temperatures from downloadable product status.

Fetching updated remote refs did not merge, reset or replace local files. A
later session must inspect actual HEAD, refs and working-tree changes before
deciding how to incorporate any newer frontend work.

At this inspection, the only tracked path changed on both sides was
`docs/datasets.md`: local changes describe external inputs, while the remote
adds acquisition provenance. Preserve both. The fetched update did not change
the paused runtime files. Recheck overlaps, including added/untracked paths,
after the next fetch; this observation is not a guarantee about later updates.

## Refresh and reconcile before runtime edits

Inspect the current state with these commands, handling required repository or
network permissions normally:

```bash
git status --short
git branch -vv
git fetch origin
git log --oneline HEAD..origin/team/a1-a2-sheng-integration
git diff --name-status HEAD..origin/team/a1-a2-sheng-integration
git diff HEAD..origin/team/a1-a2-sheng-integration -- frontend docs
git diff origin/team/a1-a2-sheng-integration..origin/sheng/frontend-mock-integration -- frontend docs
git diff -- frontend backend docs
git ls-files --others --exclude-standard
```

Inspect newly added/untracked files too; `git diff` alone does not include them.
Record the actual compared commits and distinguish remote changes from local
work. If refs have changed, inspect the relevant source and protocol changes
rather than assuming this inventory is still current.

Use the integration branch as the delivery branch. Before further feature
development, reconcile the remote code, acquisition/configuration and document
updates with the paused implementation using a recoverable, non-destructive
integration. Preserve tracked edits and untracked source/documents; a tracked
diff alone is not a complete recovery copy. Large ignored datasets and secrets
do not belong in source checkpoints. Preserve unrelated work as well.
Do not reset, clean, force-checkout, automatically stash all changes, or replace
whole frontend files with an older version. Resolve overlapping edits by
retaining both intended behaviors rather than choosing an entire side. If an
overlap cannot be resolved from source and agreed requirements, report the
exact files and continue independent checks.
Do not create commits or push merely to make integration convenient.

After reconciliation, inventory what the paused implementation already does,
run applicable checks, and fill the remaining acceptance gaps. Do not recreate
the planner, store, verifier, schemas or metadata client merely because they
are not in the old committed baseline.

## Existing frontend boundaries

Inspect the latest versions of these modules before choosing edits:

| Area | Existing files | Integration requirement |
| --- | --- | --- |
| API transport | `frontend/src/services/apiClient.ts` | Reuse relative `/api/v1` requests, structured errors, cancellation and timeout handling. NASA imagery requests remain separate. |
| Route request/decoding | `frontend/src/services/routes.ts`, `frontend/src/types/api.ts` | Preserve named coordinates, modes, finite/null metrics, request/response agreement and exact endpoints. Extend compatible computed behavior. |
| Request state | `frontend/src/services/useRoutePlanner.ts` | Preserve single-flight submission, AbortController use and stale-response protection through both POST and metadata GET. |
| Map coordinates | `frontend/src/geo/marsCoordinates.ts` | Preserve explicit Mars conventions and coordinate evidence gates. A round trip alone does not verify registration. |
| Route overlay | `frontend/src/map/routeOverlay.ts` | Preserve selection markers and seam handling. Hide computed geometry while map registration is unverified. |
| Result UI | `frontend/src/components/RoutePlannerPanel.tsx` | Extend the existing panel with source-specific status, metadata and limitations; preserve map selection interactions. |
| Map/basemap | `frontend/src/components/MarsMap.tsx`, `frontend/src/map/marsWmts.ts` | Retain NASA WMTS behavior and existing map lifecycle. |
| Baseline checks | `frontend/tests/api.test.ts`, `frontend/tests/marsCoordinates.test.ts`, `frontend/package.json` | Preserve baseline coverage and add focused integration checks. Verify current commands and dependencies before running. |

At the observed working-tree snapshot, `services/metadata.ts`,
`types/routeMetadata.ts` and `types/storedRoute.schema.json` also exist, together
with local edits to the request hook, overlay and result panel. Generated type
files identify `app.planning.export_contract` as their source. Inspect and test
these existing additions before extending them; do not generate a second
parallel metadata client or assume these files are committed/tested. Regenerate
contracts from their actual source when present and verify no schema drift.

## Required user-visible behavior

1. Selecting Start/Goal and submitting a route continues to use the existing
   frontend workflow and request shape.
2. Mock responses retain their explicit mock label and null metrics.
3. A valid computed API response may display textual distance and metadata
   even while geographic display remains blocked. A metadata retrieval failure
   must have an explicit status; it must not masquerade as complete metadata.
4. Fetch the stored record by the POST route ID. Validate schema, identity,
   request/response consistency and agreement with the planned result.
5. Never draw computed geometry through a mock-only adapter. Establish source
   registration evidence and tested conversion before enabling the overlay;
   a backend `map_alignment` field alone cannot certify the browser adapter.
6. Changing selections, mode or component lifetime invalidates stale POST and
   GET responses. Old metadata must never attach to a new route.
7. Present source/version, actual grid resolution, terrain policy, complete
   specialist names/statuses and unassessed constraints when available.

## Verification matrix

| Case | Expected behavior |
| --- | --- |
| Explicit mock response | Existing route/selection behavior and mock warning remain. |
| Computed response with matching metadata, map alignment unverified | Research result and metadata can be inspected; computed polyline remains hidden. |
| Computed response with independently verified map adapter | Validated polyline and metadata render together. |
| Wrong stored ID, mismatched request/result or malformed metadata | Reject the inconsistent record and show an actionable metadata error. |
| Selection changes during POST or metadata GET | No stale geometry, result or metadata is applied. |
| Backend no-path/unavailable/limit error | Preserve structured error codes and useful messages; no client-generated route. |
| NASA imagery unavailable | Distinguish imagery failure from local API success; report browser-map acceptance separately. |

Run `npm test` and `npm run build` against the reconciled working tree. Record
which remote frontend revision was included, what local work was retained and
whether actual browser verification ran. Successful unit/build checks do not
prove geographic alignment or browser rendering.

## Reconciliation performed on 2026-11-14

`git fetch origin` confirmed local HEAD
`a105e5176280d96a74fde30c5ac0aa4b55e2ad05` and both remote refs
`4b78b6a1b2e60a66ba0a91d362adafb28a0b234e`. There were no remote frontend or
protocol source changes from HEAD and no differences between the two remote
refs. Modified frontend hook/panel/overlay/routes and untracked metadata client,
types and schema were inspected and retained as the implementation base.

A complete non-ignored source archive, including tracked and untracked files,
plus tracked diff/status/refs was saved under
`data/cache/a0-recovery/20261114T062053Z/` before integration. Existing ignored
datasets and private profiles stayed in place. No stash, reset, checkout,
commit or branch movement was used.

The remote diff was checked and applied to `.gitignore`, the acquisition
manifest, acquisition script and setup clarification. The remote acquisition
section in `docs/datasets.md` was combined with the paused local additions.
Later setup edits document the new planner and verified Linux environment.
The remote acquisition code was incorporated but never invoked to download data.
The branch remains one commit behind by ancestry: remote content is incorporated
as working-tree changes, not a merge/fast-forward commit. No fetched remote
content remains deliberately excluded. This preserves the user's no-commit rule.

The existing metadata client was strengthened to verify artifact/mask identity
and compare POST/GET results by value independent of object key order. Generated
types/schema now describe serialized responses, including emitted default
fields. Tests exercise the actual hook's single-flight, selection/mode changes,
unmount, late POST/GET, metadata failure and result presentation. Two test-only
React renderer dependencies were added; production dependencies are unchanged.

Final checks: 25 frontend tests passed and production build passed. No browser
tool or installed browser binary was available. The coordinate constant remains
false; tests confirm the overlay hides computed geometry and retains mock
behavior. Alignment and browser acceptance are pending. See the
[full report](a0-verification-report.md) for the actual local DEM/API run.
