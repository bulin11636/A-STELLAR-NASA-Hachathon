# P1 Token-Weighted Ownership Plan

## Allocation

The remaining implementation capacity is intentionally allocated by the
available assistant-token ratio:

| Owner | Remaining token capacity | P1 implementation share |
| --- | ---: | ---: |
| Sheng | 20% | 25% |
| Sam | 60% | 75% |

This protects Sheng's remaining capacity for product decisions, frontend
integration, review, and acceptance rather than duplicating backend work.

## Shared rules

- The backend remains the source of truth for profiles, grid policy, ETA,
  assessment factors, evidence quality, hard gates, and map alignment.
- `risk_score` and `assessment_confidence` are always presented together.
- Missing, stale, incompatible, or unassessed evidence never becomes low risk.
- A5 remains an explicit `not_applicable` or `unavailable` assessment entry;
  it is not silently renumbered or removed.
- Computed geometry remains off NASA imagery until persisted route metadata says
  `map_alignment: verified` after independent WMTS/wire/DEM controls pass.

## Sheng — 25%: frontend integration and acceptance

### Implement

- Add the bounded mission-profile selector: `Safest`, `Fastest`, `Science
  priority`, and `Balanced`.
- Serialize the selected profile in plan requests and preserve it through
  recovery/replay UI.
- Render backend-owned `hard_gate_status`, `risk_score`,
  `assessment_confidence`, profile/version, and factor-level evidence state.
- Render A1-A6 factor breakdown with clear `Not applicable`, `Unavailable`,
  and `Unassessed` states; do not create browser-side scores.
- Add the bounded `Coarse`, `Standard`, and `Fine` control after Sam exposes the
  supported profile/resolution contract.
- Finish Journey Briefing wording and Route/Evidence tab hierarchy around the
  new metadata.
- Add component and integration tests for profile selection, low confidence,
  blocked/unassessed gates, missing evidence, and the verified map-overlay flow.

### Review and acceptance

- Review backend fixture/schema changes for usable, English UI copy.
- Run frontend tests, production build, and browser acceptance once Sam provides
  stable fixtures.
- Verify that computed geometry appears on NASA imagery only for a verified
  alignment fixture.

### Do not spend remaining Sheng capacity on

- DEM resampling/search implementation.
- Risk-model calibration or radiation scenario mathematics.
- NASA registration numerical controls.
- Backend persistence/restart machinery or broad API migration.

## Sam — 75%: policy, data, and backend verification

### Mission profile and planning policy

- Make `safest`, `fastest`, `science_priority`, and `balanced` durable,
  versioned backend policies.
- Define supported `Coarse`, `Standard`, and `Fine` grid/resolution profiles,
  bounds, search limits, and actual cell-size metadata.
- Persist profile/version, actual resolution, ETA assumptions, and request
  identity across route retrieval and restart.

### Assessment pipeline

- Supply validated factor inputs for A1 and, only when applicable, A3.
- Preserve A2/A4/A6 as contextual or unassessed until calibrated route-risk
  models exist.
- Enforce hard gates before weighted ranking.
- Calculate evidence-quality components: availability 25%, route coverage 35%,
  temporal applicability 20%, validation/provenance 20%.
- Never emit a comparable risk score when a non-zero risk-weighted factor is
  missing or a hard gate is blocked/unassessed.

### Map and backend verification

- Implement independent NASA WMTS/wire/DEM registration controls and justified
  tolerances.
- Emit `map_alignment: verified` only after those controls pass.
- Provide stable fixtures for verified and unverified alignment, profile variants,
  blocked/unassessed gates, low confidence, and missing specialist evidence.
- Add API, persistence, restart, formula-boundary, and integration tests.

## Delivery sequence

1. Sam stabilizes profile/resolution/assessment fixtures and backend metadata.
2. Sheng implements profile and assessment presentation against those fixtures.
3. Sam completes factor input, persistence, and map-registration controls.
4. Sheng enables the verified NASA overlay path and completes browser acceptance.
5. Jointly run the acceptance matrix before merging P1 into main.

## Joint acceptance matrix

| Scenario | Required result |
| --- | --- |
| Missing A3 or other required factor | No comparable risk score; confidence and reason visible. |
| A5 absent | Explicit `not_applicable`/`unavailable` state. |
| Hard gate blocked/unassessed | No normal route-risk comparison. |
| Low risk, low confidence | UI states assessment is insufficient; never says safe. |
| Unverified map alignment | No computed route overlay on NASA imagery. |
| Verified map alignment | Main NASA map may show computed geometry. |
