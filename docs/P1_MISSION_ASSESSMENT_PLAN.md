# P1 Mission Assessment Plan

## Purpose and scope

This is the canonical English ownership plan for the next product increment.
It follows P0 request-recovery acceptance; it does not replace P0 work still in
progress. Product UI remains English. A route is never described as safe,
validated, recommended, or optimal.

P1 improves the planning experience, makes uncertainty explicit, and introduces
a backend-owned route assessment model. It does **not** add real-time astronaut
radiation telemetry or browser-side science/risk calculation.

## Non-negotiable rules

- The backend is the sole source of truth for policy, route assessment, risk,
  confidence, evidence state, and map-registration state.
- A0 may explain or select from supported mission profiles; it must not invent
  weights, alter formulas, or bypass a hard safety gate.
- Missing, stale, incompatible, or unassessed evidence never becomes zero risk.
- A computed route remains off the NASA basemap until independent NASA
  WMTS/wire/DEM registration controls pass. Until then, an independent DEM
  route view may be used only as a clearly labelled technical view.
- `risk` and `confidence` must always be displayed together.

## Product model

### Mission profiles

The planner accepts one versioned, backend-supported profile:

`safest`, `fastest`, `science_priority`, or `balanced`.

Profiles select approved weights, resolution policy, ETA assumptions, and
search limits. They do not relax hard safety gates. User-facing controls are
bounded options, never arbitrary weight sliders.

### Assessment outputs

For a route that passes applicable gates, the backend returns:

```text
hard_gate_status: pass | blocked | unassessed
risk_score: 0..100 | null
assessment_confidence: 0..100 | null
mission_profile: profile ID plus immutable version
```

`risk_score` is a conditional, relative assessment calculated from applicable,
validated risk factors:

```text
Risk = sum(profile_weight_i * agent_risk_i)
```

It is absent when the route is blocked or cannot be meaningfully assessed.

`assessment_confidence` measures the quality of the assessment, not the
safety of the route:

```text
Confidence = sum(profile_weight_i * evidence_quality_i) * 100

evidence_quality =
  25% availability +
  35% route/spatial coverage +
  20% temporal applicability or freshness +
  20% validation and provenance completeness
```

Each component is bounded from 0 to 1 and persisted with its component values
and evidence references. A factor marked `not_applicable` by the selected
profile is excluded from the denominator. A required but unavailable factor
contributes zero confidence; it cannot be silently excluded.

### Agent applicability

- **A1 Traversability** is the current terrain feasibility source and may
  participate in a hard gate and a validated route-cost/risk factor.
- **A3 Radiation scenario** may participate only when the scenario is explicitly
  applicable to the route/profile; it is not real-time astronaut dosimetry.
- **A4 Geology/science** and **A6 Observation context** remain contextual until
  separately validated risk-factor models exist. They must not be fabricated as
  safety scores.
- **A5** must be explicitly reported as `not_applicable` or `unavailable`; do
  not renumber agent IDs or silently redistribute its weight.

## Sheng ownership: frontend and user experience

### Map and planning

- Make the map the primary, large work surface; make the side panel narrow and
  collapsible.
- Add `Fit route`, `Mission scale`, and `Regional scale` controls calibrated
  for human EVA walking distances.
- Add a map scale bar, cursor/selected coordinate display, ordered stop markers,
  and per-leg distance display.
- Provide bounded planning-resolution options in Advanced mode: `Coarse`,
  `Standard`, and `Fine`. Show the actual backend-selected cell size, coverage,
  and limits.
- Add bounded mission-profile controls: `Safest`, `Fastest`, `Science priority`,
  and `Balanced`.
- Keep the NASA-basemap computed-geometry guard until backend registration says
  `verified`; then use the main map as the sole route view and retire the
  side-panel route preview.

### Information architecture and briefing

- Reorganize the right panel into English tabs: `Plan`, `Route`, `Briefing`,
  `Evidence`, and `A0 Assistant`.
- Redesign Journey Briefing with a compact metric row (distance, estimated
  traverse time, mode, data status), then `Known conditions`, `Attention areas`,
  and `Limitations`; place policy/provenance in expandable technical details.
- Render hard-gate status, risk, confidence, selected profile/version, factor
  weight, evidence state, and an actionable low-confidence explanation.
- Render A1-A6 with public names and explicit states: `Ready`, `Partial`,
  `Unavailable`, `Unassessed`, or `Not applicable`.
- Display estimated traverse time only with the backend-supplied assumptions;
  call it an estimate, never a promise.

### Frontend verification

- Unit and component tests for tabs, scale/zoom controls, map fallback states,
  resolution/profile controls, and briefing hierarchy.
- Integration tests for `pass`, `blocked`, `unassessed`, missing evidence, mock,
  low-confidence, and backend failure states.
- Assert that unavailable/unassessed evidence cannot render as low risk or safe.

## Sam ownership: backend policy, contracts, and validation

### Contracts and policy engine

- Define versioned `mission_profile`, `hard_gate_status`, `risk_factors`,
  `assessment_confidence`, `estimated_traverse_time`, and map-registration
  metadata contracts.
- Implement fixed, documented profile weights, applicability rules, resolution
  policies, ETA assumptions, and bounds for `safest`, `fastest`,
  `science_priority`, and `balanced`.
- Implement hard gates for blocked, out-of-coverage, and required-unknown
  conditions. Gates override weighted ranking.
- Compute and persist factor-level risk, quality components, evidence IDs,
  formula version, profile version, and reasons.
- Do not integrate A4/A6 into safety risk without validated models. Do not treat
  missing evidence as zero risk.

### Planning, evidence, and registration

- Apply the selected profile only through approved backend cost policies,
  grid-resolution choices, and search limits.
- Return actual planning cell size, coverage, per-leg/total distance, and ETA
  assumptions in durable metadata.
- Provide evidence layer coverage, source, uncertainty, acquisition time, and
  availability state.
- Establish independent NASA WMTS/wire/DEM registration controls, justified
  tolerances, and browser-verifiable results. Return `map_alignment: verified`
  only after those controls pass.

### Backend verification

- Unit tests for schemas, profile selection, immutable weights, formula versions,
  risk/confidence boundaries, and invalid input.
- Tests for hard-gate precedence; missing, stale, and incompatible evidence;
  A5 state; and factor applicability.
- Persistence/retrieval/restart tests proving assessment metadata remains
  consistent with the stored route.
- Registration controls for verified and unverified map-alignment outcomes.

## Joint acceptance criteria

| Scenario | Required outcome |
| --- | --- |
| `Safest` or `Fastest` request | Uses a supported, versioned backend profile; no arbitrary client weights. |
| Hard gate fails | `blocked` or `unassessed`; no normal comparable risk score. |
| Low risk and low confidence | UI explicitly says evidence is insufficient; it does not claim safety. |
| A4/A6 contextual-only evidence | Presented as context, not a fabricated safety score. |
| A5 unavailable | Explicit status and confidence impact; never silent renumbering. |
| NASA registration unverified | No computed geometry over NASA imagery. |
| NASA registration verified | Main NASA map may display the computed route; no competing side preview. |

## Sequencing

1. Finish P0 recovery, advanced-plan-to-A0 flow, and joint acceptance.
2. Sam lands the versioned P1 assessment contract and fixtures; Sheng builds
   against fixtures in parallel.
3. Sheng delivers map layout, tabs, Journey Briefing, resolution/profile UI,
   and test coverage.
4. Sam integrates assessment/persistence/ETA and registration controls.
5. Jointly test profile, gate, risk/confidence, evidence, and map-alignment
   acceptance before enabling the NASA route overlay.


## Implementation status — 2026-11-15

The integrated `main` includes P0 recovery and the specialist-selection/walking
foundation described in [Specialist selection and walking assessment](SPECIALIST_ROUTING_AND_WALKING.md).
This status records implementation progress; the P1 requirements and acceptance
criteria above remain unchanged.

| Requirement | Current implementation | Remaining P1 work |
| --- | --- | --- |
| Explicit walking ETA | User-supplied speed, intermediate dwell, stored assumptions and revision recalculation | Adopt the versioned P1 traverse-time/profile contract |
| Specialist applicability and provenance | Bounded selection, mandatory terrain checks, required analysis enforcement and durable execution traces | Add route coverage, temporal applicability and component-level quality scoring |
| Radiation applicability | Explicitly scoped constant-rate scenario with duration, uncertainty and scenario budget outcome | Bind applicability to supported P1 mission profiles; no real-time dosimetry claim |
| Context-only science and rover evidence | Context and grounded waypoint proposals; no fabricated safety factors | Retain this boundary until separately validated factor models exist |
| Planning metadata | Actual grid resolution, coverage, total projected distance and bounded search policy | Versioned resolution options and per-leg distance output |
| Hard gates | Blocked/out-of-coverage terrain is rejected; required unknown/failed analyses are reported | Add unified `hard_gate_status`; current required-unknown output is a provisional terrain route with warnings |
| Assessment persistence | Walking/scenario assessments and specialist traces survive retrieval/restart; retries preserve identity | Add persistence fixtures and invariants for the P1 profile/factor/confidence model |
| NASA registration | `map_alignment: unverified`; computed NASA overlay remains disabled | Independent NASA registration controls and verified-state acceptance |

The four versioned mission profiles, fixed profile weights, normalized factor
risk, evidence-quality components and `assessment_confidence` are not implemented.
The existing nullable `metrics.risk_score` contract is 0..1; the P1 contract must
explicitly accommodate the required 0..100 scale. The former A5 responsibility
currently belongs to A1, but a separate A5 `not_applicable`/`unavailable` assessment
entry and confidence treatment are still required by this plan.

Frontend P1 tabs, Journey Briefing, profile/resolution controls and paired
risk/confidence presentation remain pending. Existing stop focus, preview zoom,
walking controls and specialist traces are supporting features, not complete P1
frontend acceptance. See the linked delivery guide for the existing offline test
results; those tests do not certify the remaining P1 assessment model.
