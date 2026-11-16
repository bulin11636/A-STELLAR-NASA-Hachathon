# Architecture

A-STELLAR is a React/OpenLayers workspace backed by FastAPI, explicitly registered
scientific workers and a deterministic terrain planner. The public computed
route path uses ordinary Python orchestration. A separate optional LangGraph
experiment exists under `app.coordinator`; it is not required to start the web
application or compute its A* routes.

## Runtime components

| Component | Responsibility |
| --- | --- |
| `frontend/src/components/` | Planning, route inspection, evidence controls, Mission Planner conversation and briefing |
| `frontend/src/services/` | Typed relative API requests, cancellation, response validation and recovery |
| `backend/app/api/` | HTTP validation, readiness, route/chat endpoints and bounded map resources |
| `backend/app/coordinator/route_agent.py` | Public route coordinator: specialist selection, bounded proposals and host execution |
| `backend/app/coordinator/specialists.py` | Advertised capabilities, required analyses and auditable specialist execution |
| `backend/app/agents/` | Explicit async worker registry and typed scientific adapters |
| `backend/app/planning/` | Source grids, conservative regional aggregation, A*, native checks and assessment |
| `backend/app/planning/store.py` | Complete route records, immutable artifacts and integrity checks |

In Docker, FastAPI serves the production frontend and API on one origin. During
development, Vite proxies `/api` to port 8000. Scientific data and the runtime
configuration are mounted separately; persistent application state has its own
volume. See [Docker](docker.md).

## Route lifecycle

1. Validate coordinates, ordered visits, mission inputs and supported policy choices.
2. Prepare a grid from the configured DEM. The initial example window is not
   the full supported regional footprint.
3. Run mandatory terrain checks and select applicable optional specialists.
   In agentic mode, allowlisted model proposals guide selection and explanation.
4. Reject proposals that change explicit inputs or introduce unknown coordinates,
   unsupported actions, invalid fields or unavailable citations.
5. Solve each required route leg in order using deterministic A*. Check its
   connectors and segments against native terrain cells.
6. Derive walking time from explicit assumptions. Evaluate an applicable
   radiation scenario after duration becomes available, then assess evidence.
7. Publish a complete stored result with metadata, rationale, trace and artifacts.
   Return a route ID that the frontend can retrieve independently.

The model cannot execute code, choose arbitrary files/URLs, change host policy,
or supply authoritative geometry. Deterministic mode skips model generation;
its conversation functionality is narrower. The [agent guide](agents.md)
describes specialist selection and interpretation.

## Terrain and regional planning

The host-approved profile defines source identity, units, an initial window,
slope threshold, terrain penalty, resolution policy and search budgets. Unknown
or NoData cells are impassable. Eight-connected A* uses projected metric edge
lengths and rejects blocked diagonal corners. A terrain-penalized objective adds
a documented nonnegative slope cost; it is not a calibrated EVA safety model.

Regional requests can use dynamic crops and conservative aggregation across the
supported source. Request size, node count and elapsed search time remain bounded.
Aggregation never substitutes a visually enlarged map image for scientific data.
Emitted segments are checked against the native raster, including endpoint
connectors. Source/profile changes require rebuilding the grid consistently.

A failed connection can trigger a bounded broader source crop without another
model call. Search/profile limits and actual cell size are persisted; the client
must not infer them from a requested resolution label.

## Assessment semantics

The backend owns versioned mission-profile weights, gates, risk factors and
confidence. Factors retain explicit assessed, contextual, unavailable, stale,
incompatible, unassessed and not-applicable states.

- Complete comparable risk is withheld when required weighted factors are missing
  or a mission gate is blocked/unassessed.
- `partial_risk_score` summarizes only assessed factors with applicable risk
  weights. Its `risk_evidence_coverage` is the known profile weight, not a
  geographic coverage fraction or accident probability.
- Assessment confidence is a separate evidence-quality score. Its components are
  availability, route coverage, temporal applicability and validation/provenance.
- A blocked gate remains blocked even if a partial score is available.
- Geological and rover context do not automatically become calibrated risk costs.
  Surface-obstacle context is merged into terrain analysis.

Walking time uses supplied speed and per-intermediate-visit dwell. It excludes
slope-dependent pace, rest, physiology, suit/load and life-support models.
Radiation scenario pass/fail/unknown is limited to the configured scenario.

## Map presentation

The frontend presents Viking global imagery, a separate Jezero mosaic and
available local scientific previews. Radiation scenarios are non-spatial.
Map visibility and opacity do not change route costs. Some POI/traverse layers
are selected fixture subsets; local raster previews are display products rather
than native analysis grids.

Computed polylines are currently demo overlays after coordinate conversion.
Scientific pixel registration is a separate metadata/verification result.
See [map registration](map-registration.md) for coordinate conventions and the
independent measurement procedure.

NASA imagery is fetched through a same-origin endpoint restricted to the
allowlisted layers and validated resource paths. The service bounds responses
and caches resources; it is not an arbitrary URL proxy. Local raster rendering
also uses allowlisted files rather than client-supplied paths.

## Persistence and request recovery

Each successful route retains its request, geometry, measured metrics, grid,
policy, sources, validation, worker trace, rationale and applicable model usage.
A revision stores a parent route ID. Retrieval checks schema, identity and
artifact consistency; partial publication must not appear as a complete route.

Keyed requests retain running, succeeded, failed or unknown states. A repeated
successful request can recover its saved response without generation. An eligible
failed request requires an explicit versioned retry; an unknown outcome does not
grant permission for automatic execution. HTTP cancellation stops client waiting,
not necessarily backend work. See [API recovery](api.md#request-recovery).

Raw rasters and private runtime files stay outside tracked source. Arrays and
large scientific products remain local artifacts; only bounded facts, evidence
IDs and approved context reach the model. The packaged
[`SKILL.md`](../backend/app/coordinator/skills/mission-coordinator/SKILL.md) belongs
to the optional coordinator experiment and remains an application asset.

## Extending the system

A new specialist needs an explicit typed contract, scope/provenance checks,
registration in the authored-worker allowlist, bounded execution, and tests for
missing as well as successful inputs. Adding a new internal ID requires changing
the relevant schemas/allowlists; dropping a Python file into the repository does
not automatically enable it.

A spatial layer also needs a validated display extent and a browser-consumable
artifact. A new routing cost or hard constraint requires separate numerical and
scientific validation. This separation supports new sensors, analyses and regions
without treating every new visual layer as an established safety signal.

Future regional support could focus the same layer and specialist structure on
other Mars craters or landing sites. It requires region-specific terrain,
imagery, evidence, coordinate transforms and registration, together with changes
to the current Jezero-specific API contracts and configuration.

Future live-data support could ingest time-stamped sensor or mission updates,
refresh specialist evidence, and trigger A* replanning when validated routing
costs or constraints change. Updated routes and assignments would retain their
source timestamps, reasons and revision history. Real-time route allocation
would require feed adapters, freshness policies, update triggers and suitable
communications and processing latency. The current implementation uses
configured inputs and request-driven planning.
