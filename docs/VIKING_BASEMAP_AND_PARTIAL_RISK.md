# Viking imagery and available-factor risk

The global background now uses the same equirectangular default as Mars Trek:
`Mars_Viking_MDIM21_ClrMosaic_global_232m`, a Viking VIS global visible-light
image mosaic. The reference is NASA's live
[basemap configuration](https://trek.nasa.gov/mars/jpl/config/basemapList.json).
Its WMTS metadata and a real JPEG tile were checked against the NASA service.
The separate Jezero HiRISE/CTX/HRSC overlay remains available. M20 DEM terrain
calculations are unchanged. Attribution, layer descriptions and the app header
now identify Viking imagery rather than MOLA colorized elevation.

The view can zoom beyond the coarse global tile grid so the local Jezero
imagery and mission stops remain usable at walking scale. Enlarging a global
tile does not increase its source resolution. NASA resources are served through
`/api/v1/map/nasa/{layer_id}/...` using two fixed allowlisted layer identifiers,
validated tile indices, bounded responses and a small in-memory cache. No
credentials or arbitrary upstream URLs are accepted by this route.

Only available spatial layers appear in the map control list. Non-spatial A3
radiation scenarios remain part of route assessment/briefing rather than map
layers. Spatial groups remain in A1, A2, A4 and A6 order; A5 is merged into A1.
User-facing labels omit internal agent identifiers. The interface uses Mission
Planning Assistant, Terrain & Traversability, Thermal Environment, Radiation
Exposure, Geology & Science, Surface Obstacles, and Rover Operations &
Observations. Internal protocol IDs are retained for compatibility; dynamic
messages, warnings, specialist traces and recovery errors use display names.

## Partial risk

Complete risk retains the existing weighted formula and mission gate. A
separate `partial_risk_score` is now displayed when any applicable weighted risk
factor has been assessed:

```text
known_weight = sum(profile weights for assessed risk factors with scores)
partial_risk_score = 100 * sum(weight * factor_score) / known_weight
risk_evidence_coverage = 100 * known_weight
```

Factor scores are 0–1; displayed risk scores are 0–100. Missing factors are
excluded from both numerator and denominator, never assumed to be zero risk.
With only A1 assessed under Safest, a terrain score of 0.4 is displayed as
`40 / 100 (partial)` with `75% of profile risk weight` covered. Assessment
confidence remains a separate evidence-quality score and is not used as a risk
value. This weight coverage is not geographic coverage or the probability of
an accident. A complete assessment gives the same partial and complete scores.
Zero assessed risk stays zero; no assessed weighted factors stays unknown. A
blocked mission gate remains visible even when known-factor scores exist.

The backend derives these optional fields while validating both new and older
stored routes, without rewriting original scientific artifacts or making a
model request. Supplied inconsistent partial values are rejected. Frontend
response schemas and types are generated using the existing
`python -m app.planning.export_contract` command and accept older records that
do not contain these fields. Route, Plan, Briefing and briefing exports display
the same backend-derived values.

Verification covers missing/complete/zero/blocked cases, all four mission
profile weights, backward-compatible stored routes, schema generation, proxy
URL bounds/cache behavior and UI rendering. Browser workflows use mocked A0
responses; `--live-nasa` additionally checks real NASA imagery delivery.

Local verification on 2026-11-15: 438 backend tests, 94 frontend tests, type
checking and production build passed. The browser regression flow received a
real Viking tile and checked all five tabs, responsive briefing layout and
budget recovery without paid model calls. The route workflow passed eight-stop
edits, history reload and a 60 km regional route. An earlier concurrent run
returned a route storage error that did not recur on the independent rerun;
route publication now logs the private exception for diagnosis if it recurs.
