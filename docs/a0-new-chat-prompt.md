# New-chat implementation and test prompt

Latest checkpoint: read [regional verification](regional-verification.md),
[the agent/chat guide](a0-agent-chat.md), [Docker runtime](docker.md) and
[the TODO](TODO.md). Preserve the current implementation and working tree.

## Current handoff prompt

```text
Work from this repository root on team/a1-a2-sheng-integration.
Read repository instructions, docs/TODO.md, docs/regional-verification.md,
docs/a0-agent-chat.md and docs/docker.md before changing behavior. Repository
documentation must be English. Keep TODO.md limited to pending work; exclude
personal usage, subscription and billing information.

Continue the existing FastAPI/React implementation. Computed routes support
native crops and full-source conservative adaptive A*, independent native
segment checks, up to 16 ordered waypoints, persisted rationale and chat
revisions. Disconnected crops can retry the full source under the same search
budget without another model call. The UI has parent comparisons and a
fit/focus/zoom/pan/expand DEM preview. NASA computed overlays remain gated.

Use the checked-in regional and browser verifiers with real local DEM inputs
and mocked model responses. Rebuild production frontend assets before browser
tests. Never expose .env contents or send real credentials to browser/tests.
Live-provider acceptance remains blocked by HTTP 429 unless resolved in this
session. Docker files exist, but actual engine build/mount/restart acceptance
must be established on an available engine; local HTTP tests are insufficient.

Inspect git status and fetch remote updates before reconciling work. Preserve
other changes and source evidence. Do not rewrite history or push unless the
current user authorizes it. Complete the selected pending work and report what
passed, what remains unverified and reproducible commands.
```

## Historical milestone prompt

Scope note (2026-11-14): this prompt preserves the earlier deterministic milestone.
The user's subsequent requirements are reflected in the implementation and
current guides. The TODO lists remaining work only. The historical "no live LLM"
scope below is superseded by the current handoff and session instructions.

The following prompt authorizes resuming the paused local A0 implementation,
reconciling remote updates, and completing verification of the approved milestone.
The user paused development when remote updates appeared. Existing local code
is unfinished work to continue, not an empty starting point or an active writer.
Paste the complete block into a new Codex chat with this repository open.

```text
Work in /home/sam/nasa/repo/A-STELLAR on team/a1-a2-sheng-integration.

Resume my paused local implementation of the approved deterministic A0
route-planning milestone, reconcile remote updates, then complete it and test it.
Read applicable AGENTS.md instructions, inspect git status, and preserve all
unrelated changes and existing handoff documents, including uncommitted files.
Do not commit, push, publish or deploy unless I request it.

I paused this development because the remote branch was updated. Treat the
modified and untracked local backend/frontend files as my partially completed
implementation. Do not discard them or start the milestone again from scratch.

Before runtime edits, fetch origin and inspect the latest integration branch
and origin/sheng/frontend-mock-integration. Compare frontend/protocol changes
with both HEAD and the local working tree, including untracked files. Read
docs/a0-frontend-integration.md for the observed baseline and refresh procedure.
Integrate relevant remote code, acquisition/configuration and documentation
updates before resuming feature development, preserving paused local changes.
Inspect overlaps first and use a recoverable integration that includes untracked
source files; do not reset, force-checkout or automatically stash the workspace.
Existing local A0 and metadata-client implementation is partially complete:
inspect, reuse and verify it, then implement the remaining gaps. Do not rebuild
the frontend from an older snapshot or create duplicate clients/components.

Read these repository documents before editing runtime code:
- docs/a0-implementation-plan.md
- docs/a0-api-contract.md
- docs/a0-verification.md
- docs/a0-frontend-integration.md
- docs/architecture.md
- docs/agents.md
- docs/datasets.md
- docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md
- docs/A_STELLAR_JEZERO_TEAM_BACKEND_MASTER_PLAN.md

The a0-* documents record my approved next milestone. The original protocol's
mock-only milestone is the baseline, not a reason to leave real routing undone.
Implement the documented API additions in backend and frontend together while
preserving existing field meanings and explicit mock compatibility.
Use the reconciled current frontend and its existing API transport, selection
workflow, cancellation, coordinate adapters and overlay as the integration base.

Deliver real DEM ingestion for one small verified Jezero ROI, a canonical
metric traversability grid with coverage/unknown/blocked masks, bounded A*,
independent route validation, durable local result/metadata storage, the
existing POST /api/v1/routes/plan in computed mode, and the new
GET /api/v1/routes/{route_id}. Integrate typed metadata retrieval and computed
route display in the frontend after proving map/wire/DEM alignment.

Use ordinary Python orchestration for the main pipeline. Keep internal A0,
A1, A2, A3, A4 and A6 IDs and use the complete public names and responsibility
descriptions in the approved plan. A5 stays merged into A1. Preserve the
existing optional LangGraph experiment; do not require it for real routing.
Do not call a live LLM, request an API key or add natural-language parsing.

Inspect ~/nasa/project/dataset for the supplied A1/A2 rasters and any completed
A3/A4/A6 downloads. Use explicit local configuration and bounded raster windows.
Do not move large inputs, commit datasets, download archives automatically or
depend on a temporary helper from another chat. Missing optional evidence must
remain unavailable/unassessed and must not prevent terrain-only routing.
Treat existing A1/A2 outputs as prototypes until their geometry and units are
verified. Do not feed the old raw slope artifact directly into A*.

Do not bypass coordinate guards, treat Mars as Earth EPSG:4326, invent fine
resolution, route through NoData, cut blocked corners, append unchecked endpoint
connectors, fabricate metrics, or silently fall back to a mock in computed mode.
Keep unknown time/risk null. Persist source/version, transforms, resolution,
policy, planner/validator details and artifact identifiers as specified.

After reconciling remote updates, assess the resumed implementation against the
acceptance criteria. Run baseline checks, complete missing work, then perform the meaningful tests
and explicit real local DEM/API/restart-persistence run in the verification
guide. Check A* against independent Dijkstra costs on small synthetic grids.
Provide a reproducible local verification command and exact real request JSON.
Run frontend tests and build; verify browser display when tools permit. Keep
the display guard and report pending acceptance if alignment cannot be proven.
Existing scripted A0 tests alone do not satisfy this task.

Write all new or edited repository documentation in English. Update docs to
match implemented behavior and save an English verification report with actual
commands, versions, checks, route IDs, artifacts and remaining blockers. Never
claim a real-data, browser or live-model test that did not run. Continue through
implementation and verification; ask only for a genuine blocker that cannot
be resolved from the repository and available local inputs.
Record the compared/integrated frontend revisions and any unmerged remote
changes or preserved local work that affect acceptance.
```

## Verification-only use after implementation

If a later chat should only inspect an already implemented milestone, replace
the opening task sentence with:

```text
Verify the implemented deterministic A0 milestone against the three a0-* plan,
API and verification documents. Do not change runtime code unless I request a
fix. Run applicable existing checks and the explicit real-data verification
command, inspect persisted results and metadata, and report each acceptance
item. Missing implementation is a failed/pending item, not a passing mock test.
```

For that verification-only use, omit the implementation/delivery instructions
from the main prompt; retain the branch, local-data, English-documentation,
no-live-model, honest-reporting and preservation constraints.
