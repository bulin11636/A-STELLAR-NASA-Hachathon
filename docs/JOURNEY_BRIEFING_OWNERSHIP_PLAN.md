# Journey Briefing Ownership Plan

## Goal

After a route is available, show a concise **Journey Briefing** describing known
conditions, evidence status, planning limitations, and—only when backend evidence
exists—specific route attention areas. The UI must not manufacture a risk score,
infer hazards from a map line, or describe a route as safe.

## Current sequencing

- Sam is currently testing the integrated P0 branch.
- Sheng can start the existing-metadata briefing work immediately.
- After P0 integration passes, Sam implements the new segment-hazard contract.
- Sheng then connects the new typed hazard payload and enables attention-area UI.

## Sheng work

### Phase S1 — Existing metadata briefing (start now)

- [ ] Extend the existing `MissionBriefing` into a route-specific **Journey Briefing**.
- [ ] Render route summary: route ID, source, objective, measured distance when
  available, ordered required waypoints, DEM/grid resolution, and dataset version.
- [ ] Render planning conditions from metadata: policy ID, slope threshold,
  unknown-cell handling, corner-cutting policy, bounded search limits, and map
  registration state.
- [ ] Render warnings and rationale in separate **Known limitations** and
  **Planning rationale** sections.
- [ ] Render A1–A6 worker status with explicit values such as `ready`, `partial`,
  `unavailable`, and `unassessed`.
- [ ] In mock mode, show **Demo only — no terrain risk assessment is available**.
- [ ] In computed mode without segment hazards, show **No segment-level hazard
  assessment was supplied by the backend**.
- [ ] Keep all UI text in English.

### Phase S2 — Typed hazard UI (after Sam contract lands)

- [ ] Add a strict decoder for `route_hazards`.
- [ ] Display attention areas ordered by `route_segment_index`.
- [ ] Show severity, status, evidence reference, concise backend message, and
  whether the item is derived, observed, unavailable, or unassessed.
- [ ] Keep computed geometry off the unverified NASA basemap; use the independent
  DEM route preview for any segment focus interaction.
- [ ] Never render a missing hazard list as proof that no hazards exist.

### Sheng tests

- [ ] Mock route shows demo/no-risk-assessment label and no fake hazards.
- [ ] Computed metadata renders policy, rationale, worker state, and warnings.
- [ ] Missing A2/A3/A4/A6 evidence renders `unassessed` or `unavailable`, not safe.
- [ ] Malformed hazard payload is rejected with an actionable metadata error.
- [ ] Hazard UI preserves backend ordering and does not alter route geometry.

## Sam work

### Phase A — Do after current P0 integration test passes

- [ ] Define a durable typed `route_hazards` payload for computed routes.
- [ ] Produce hazards only from validated backend route/DEM evidence.
- [ ] Add hazard data to stored route metadata or a versioned route-detail endpoint;
  do not require frontend inference.
- [ ] Preserve route persistence, route retrieval, and restart behavior.

### Required contract

```json
{
  "route_hazards": [
    {
      "hazard_id": "string",
      "route_segment_index": 12,
      "kind": "steep_slope | blocked_proximity | unknown_proximity | validation_limit",
      "severity": "high | medium | low | unknown",
      "status": "derived | observed | unavailable | unassessed",
      "message": "English backend-grounded explanation.",
      "evidence_ids": ["string"],
      "source": "A1 | planner | validator"
    }
  ]
}
```

### Backend validation rules

- [ ] `route_segment_index` must refer to an emitted route segment.
- [ ] A `high` or `medium` severity must have a non-empty grounded message and
  applicable evidence/source reference.
- [ ] `unknown`, `unavailable`, and `unassessed` never become `low` by default.
- [ ] A missing/empty list means no segment assessment was supplied; it does not
  certify a hazard-free route.
- [ ] A2/A3/A4/A6 cannot automatically create terrain-risk severity without a
  separately validated policy.
- [ ] No map registration claim is inferred from route hazard data.

### Sam tests

- [ ] Valid computed route persists/retrieves ordered hazards after restart.
- [ ] Bad segment index, invalid severity/status, missing evidence for high/medium,
  and malformed payload fail validation.
- [ ] Mock routes contain no computed hazard claim.
- [ ] NoData/unknown/blocked/near-threshold cases remain correctly labeled.

## Joint acceptance

| Scenario | Required result |
| --- | --- |
| Mock route | Demo label; no fabricated route risk. |
| Computed route without hazards | Conditions/limitations visible; explicitly no segment assessment. |
| Computed route with validated hazards | Ordered attention areas shown from backend payload only. |
| Missing specialist evidence | Explicit unavailable/unassessed status, never a low-risk claim. |
| NASA basemap unverified | No computed geometry overlay; briefing remains usable. |

## Non-goals

- Browser-side terrain risk calculation or image interpretation.
- Automatic re-routing based on a briefing card.
- Astronaut safety certification.
- Rendering a backend hazard as a visually aligned NASA basemap location before
  independent WMTS/wire/DEM registration is verified.
