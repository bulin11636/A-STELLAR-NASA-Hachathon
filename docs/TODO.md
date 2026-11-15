# TODO

## P0 frontend integration and acceptance

- [ ] Revalidate map fitting, nearby-stop usability and the supported route view after the frontend owner's presentation changes; retain the unverified NASA registration status until independent registration checks pass.
- [ ] Revalidate active-mode labels, actionable failures and unassessed evidence after the frontend owner's presentation changes.

- [ ] Complete Sheng's Quick/Advanced controls, required-waypoint interactions and plan-to-chat flow against the shared P0 fixtures and backend.
- [ ] Integrate request status, stable IDs and explicit versioned retry controls without automatic model retries; run the joint P0 acceptance matrix.

## Deferred: deployment operations

- [ ] Document and exercise backup/restore and upgrades for persistent application state.

## Deferred: route revisions and chat

- [ ] Support explicit avoidance areas with typed geometry, bounded masks and independent validation.
- [ ] Define optional visits, soft preferences and unspecified visit order without weakening required constraints.
- [ ] Add cooperative cancellation for specialist/model/planning work and expose progress without applying stale results.
- [ ] Support longer conversations with bounded, source-grounded summaries and retained typed preferences.

## Deferred: planning coverage

- [ ] Refine narrow passages or endpoint neighborhoods excluded by conservative regional aggregation while retaining bounded native validation.
- [ ] Discover generic example endpoints for supported profiles beyond the explicit CTX/Jezero demonstrations.
- [ ] Verify other DEMs' source identity, units, datum, masks and registration before integration.

## Deferred: NASA map registration

- [ ] Establish independent NASA map/wire/DEM controls with justified tolerances.
- [ ] Resolve the source-radius discrepancy and NASA latitude semantics.
- [ ] Verify computed NASA route alignment and tile behavior in a real browser after registration is established.

## Deferred: specialist evidence

- [ ] Bind required mission constraints explicitly and distinguish missing, stale, incompatible and unassessed evidence.
- [ ] Define how compatible evidence affects costs, mission constraints or waypoint selection.
- [ ] Replace A2 visual-raster heuristics with calibrated observations before supporting thermal constraints.
- [ ] Provide a supported A3 scenario/model with explicit duration, units and applicability; keep rejected RAD products excluded.
- [ ] Revalidate A4 geology associations and define a reproducible science-priority rubric.
- [ ] Verify A6 localization/clock joins and observation links for the selected release.
- [ ] Complete provenance for local inputs with missing receipts or embedded unit metadata.

## Deferred: provider integration and quality

- [ ] Evaluate live-model interpretation of removals and ambiguous places beyond the explicit additions and reordering required for the demo.
- [ ] Support explicitly configured model adapters and validate their capabilities before use.
- [ ] Replace the conservative serialized-input guard with tested tokenizer-based context accounting.
- [ ] Migrate deprecated React renderer tests to a maintained DOM testing approach.
