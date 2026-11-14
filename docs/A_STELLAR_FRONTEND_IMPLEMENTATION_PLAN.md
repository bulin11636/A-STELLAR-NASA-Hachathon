# A-STELLAR — Jezero Frontend Implementation Plan

**Status:** Implementation specification / Codex handoff  
**Scope:** Frontend only; do not change the backend  
**Primary region:** Jezero Crater, Mars  
**Stack:** Existing React + TypeScript + OpenLayers project  
**Owner:** Frontend developer  
**Backend dependency:** Existing agreed API contract; mock adapters until specialist services are ready

## 1. Product goal

Build an **evidence-first Jezero EVA Science Briefing interface**. The UI lets a human select an exploration area, inspect NASA/USGS data and provenance, mark mission objectives, inspect a demonstration route, and ask a conversational assistant to **explain or request changes** to a route. It must **not** claim the route is safe, optimal, recommended, or validated until the backend supplies appropriate validated evidence.

### Success path
1. Open a real NASA Mars Trek basemap focused on Jezero.
2. Toggle available layers and inspect status, provenance, uncertainty, and coverage.
3. Select Start, Goal, and optionally Science POIs.
4. Call the existing `POST /api/v1/routes/plan` endpoint or its mock adapter; draw a **DEMONSTRATION ROUTE — NOT SAFETY VALIDATED**.
5. Click a location or route segment to see point-level evidence and unknowns.
6. Open the Mission Assistant; ask *Why this route?*, *Find a shorter alternative*, *Avoid this area*, or *What did Perseverance observe nearby?*
7. Preview any proposed route change; do not silently replace the current route.

## 2. Non-goals and guardrails

- Do **not** implement A0 LLM, A1/A2/A3/A4/A6 computations, A*, risk fusion, DEM processing, or NASA data ingestion in the frontend.
- Do **not** fabricate thermal heatmaps, radiation spatial grids, hazard certainty, scores, or rover observations.
- Distinguish **source observations** from **derived calculations** and **demo fixtures**.
- No autonomous action on user chat text: changes become **candidate** routes requiring explicit Accept/Reject.
- Preserve the already-working Mars Trek WMTS map and current backend paths.
- Keep credentials / LLM API keys out of browser code.

## 3. Existing integration contract

Do not break or rename:
- `GET /api/v1/health`
- `GET /api/v1/regions`
- `POST /api/v1/routes/plan`

Keep the existing request/response schema from `docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md` as authoritative. Do not invent a replacement coordinate convention. The previously agreed convention is **`MARS_2000_PLANETOCENTRIC_EAST_360_V1`**; verify against the repo document and use explicit conversion at OpenLayers boundaries. Never treat Mars positions as terrestrial WGS84 distances or blindly call earth-centric `fromLonLat()`.

**Future proposal only (not required by current backend):** `POST /api/v1/mission/chat` for A0. Agree with backend owner before implementing real network behavior. For now provide mock chat via the repository interface described below.

### Proposed chat contract (future, draft)

Request:
```json
{
  "session_id": "eva-demo-001",
  "route_id": "route-demo-001",
  "message": "Why does the route detour?",
  "context": {
    "region_id": "jezero",
    "selected_location": null,
    "start": null,
    "goal": null,
    "active_layer_ids": ["mars_basemap", "geology"],
    "avoid_geometry": null
  }
}
```

Response:
```json
{
  "reply": "This is a demonstration route. Terrain-derived reasons are not yet available.",
  "intent": "EXPLAIN_ROUTE",
  "route_updated": false,
  "candidate_route": null,
  "evidence_refs": [],
  "warnings": ["Terrain safety has not been validated."],
  "planning_status": "mock"
}
```

**Important:** The chat schema is a frontend-owned proposal until ratified. Keep it behind a mock adapter; don't assume the backend already supports it.

## 4. Information architecture and UI components

### 4.1 Main map
- Preserve OpenLayers and NASA Mars Trek WMTS.
- Default viewport: Jezero, using an explicitly documented Mars coordinate convention.
- Layer visibility, order, opacity, legend, status, source link, temporal/coverage metadata.
- Overlay markers for Start, Goal, candidate Science POIs, Perseverance traverse and Sol locations, and current/candidate routes.
- Visual differentiation: current route = dashed amber; candidate = distinct dashed style; no green “safe” route.

### 4.2 Layer & evidence panel
Minimum planned entries (availability is data-driven, not assumed):

| Layer | Data family | Label policy | Notes |
|---|---|---|---|
| Mars Trek basemap | Optical/context | Observed source imagery | Visual context only |
| Jezero DEM coverage | Topographic | Observed source / prototype derived slope | Coverage ≠ validated traversability |
| USGS SIM 3464 geology & Science POIs | Geology/science | Observed source / prototype POI scoring | Regional units have uncertainty |
| Perseverance traverse & Navcam references | Historical rover observations | Observed historical | Rover traversal ≠ astronaut safety |
| Radiation dose scenario | Mission-level environmental model | Scenario | Non-spatial; no fake heatmap |
| Thermal | Thermal | Unavailable / prototype until calibrated data is ready | No fake heatmap |

**Evidence status enum:** `observed | scenario | prototype | unavailable`; include an additional `validation_status` (e.g. `not_validated | validated_for_demo`) where appropriate. Source metadata must distinguish observation date, publication date, ingestion date, spatial resolution, units, coordinate convention, source URL and known limitations; values may be `null`.

### 4.3 Evidence-at-point drawer
On map click show selected Mars lon/lat and, if supported by fixture/index:
- applicable geologic unit, with ambiguity/coverage disclaimer;
- nearest Perseverance traverse segment or Sol and distance (only with Mars-compatible geometry);
- available Navcam browse references, with source links;
- DEM footprint and metadata, not invented elevation values;
- unsupported/unknown data states and uncertainties.

### 4.4 Mission briefing panel
- Objective, selected Start/Goal, mission POIs and route identifier.
- Demonstration route indicator and any available distance/time **with provenance**.
- Evidence sources, limitations, unknowns, warnings.
- Export simple JSON (first); optional print-friendly HTML/PDF only after UI is stable.

### 4.5 Conversational Mission Assistant
Use a chat panel, **not a browser-side LLM agent**. Backend A0 owns LLM reasoning later.

Supported intents / quick prompts:
- `EXPLAIN_ROUTE`: “Why did this route detour?”
- `MODIFY_ROUTE`: “Can you find a shorter alternative?”
- `QUERY_EVIDENCE`: “What did Perseverance see here?”
- `EXPLAIN_RISK`: “Which hazards are known vs unknown?”
- optional `AVOID_AREA`: map-drawn polygon request; only after polygon UI is available.

Required UX:
- send chat context with current route id, region, selections, layer ids and selected point;
- show assistant responses with provenance links and warnings;
- display mock/prototype/unavailable clearly;
- candidate route preview + **Accept / Reject** controls; never automatically mutate current route;
- request loading, empty, timeout, error and retry states;
- no hallucinated route explanation from the mock adapter; template-based response saying analysis is pending.

## 5. Types and repository abstraction

Suggested structure (adapt to existing folders rather than rewriting the app):
```text
frontend/src/
  components/
    LayerPanel/
    EvidenceDrawer/
    MissionBriefing/
    MissionAssistant/
    RouteControls/
  map/
    MarsMap.tsx
    layerRegistry.ts
    overlayManager.ts
  services/
    missionRepository.ts
    mockMissionRepository.ts
    apiMissionRepository.ts
    chatRepository.ts
    mockChatRepository.ts
  types/
    evidence.ts
    layers.ts
    mission.ts
    chat.ts
  fixtures/
    README.md
    sample-science-pois.geojson
    sample-rover-traverse.geojson
    sample-evidence.json
```

Keep interfaces independent of React components, for example:
```ts
interface MissionRepository {
  getRegions(): Promise<Region[]>;
  planRoute(request: PlanRouteRequest): Promise<PlanRouteResponse>;
  getSciencePOIs(regionId: string): Promise<GeoJSON.FeatureCollection>;
  getRoverTraverse(regionId: string): Promise<GeoJSON.FeatureCollection>;
  getEvidenceAtPoint(point: MarsPoint): Promise<LocationEvidence>;
}

interface ChatRepository {
  sendMessage(request: ChatRequest): Promise<ChatResponse>;
}
```

All real vs fake data must be explicit:
```ts
type EvidenceState = 'observed' | 'scenario' | 'prototype' | 'unavailable';
type DataOrigin = 'official_source' | 'derived_from_official_source' | 'synthetic_demo';
```

Fixtures derived from external data need attribution, exact source URL, data date, coordinate convention, and processing notes; synthetic demo POIs/traverses should be conspicuously labeled and never presented as actual NASA positions.

## 6. Implementation phases and acceptance criteria

### F2 — Layer registry + provenance (P0)
**Tasks:** TypeScript types, layer registry, switch visibility, opacity, legend and metadata drawer; make unavailable layers non-activatable.

**Done when:** working basemap unaffected; all layer cards show status/source/limitations; missing layers do not silently render; unit tests for status rendering.

### F3 — Science and rover overlays (P0)
**Tasks:** GeoJSON overlay renderer; science POI markers; rover historical polyline, Sol markers, observation links; fixture validation and source labels.

**Done when:** independently togglable overlays on Jezero, correct coordinate alignment and click handling, with clear demo vs observed labels.

### F4 — Evidence-at-point (P0)
**Tasks:** map click selection, point drawer, coverage/ambiguity logic (mock repository), links and unknown states.

**Done when:** clicking an arbitrary point yields either supported evidence or honest `unknown/unavailable` messages. No invented coordinates or hazard certainty.

### F5 — Mission briefing (P0)
**Tasks:** mission objective, selections, route display with DEMONSTRATION banner, evidence/warning summary, JSON export.

**Done when:** exports reflect UI state and metadata; no unverified “safe”, “optimal” or “recommended” wording.

### F6 — Chatbot UI and mock behavior (P0)
**Tasks:** chat log, input, quick prompts, context serialization, MockChatRepository, cited response cards, loading/error/retry, candidate route Accept/Reject.

**Done when:** at least four intents are demonstrable offline without a live LLM; backend remains unchanged; no auto-accepted candidate routes. Mock answers never pretend to have run actual A0/A1–A6.

### F7 — Existing route API hookup (P1)
**Tasks:** reuse `/api/v1/routes/plan`, Vite proxy if already in use, preserve request/response contract, draw route overlay with status/warnings; fallback demo repository.

**Done when:** live mock backend route works end-to-end or explicit offline mode works; API failures are visible; tests cover request and map state.

### F8 — Real A0 chat integration (BLOCKED until backend ready)
**Tasks:** jointly approve `/api/v1/mission/chat` contract; implement ApiChatRepository; handle context, route candidate and errors. Optional streaming later.

**Done when:** A0 answers only from returned backend evidence; replan candidates reference planner results and need explicit acceptance.

### F9 — Integration / UX / demo (P1)
**Tasks:** responsive layout, keyboard navigation, source links, accessibility, scenario walkthrough, regression tests, demo script.

**Done when:** a judge can inspect layers, select POI/start/goal, see demo route, ask why/modify it, inspect evidence and export a briefing without misinterpreting validation status.

## 7. Parallel development contract

**Frontend owner:** Implement map UI, fixtures, chat UI, data adapters, and evidence representation. Do not edit backend agent modules.

**Backend owners:** Continue A0/A1/A2/A3/A4/A6, risk fusion and path planning behind the existing API. Supply validated metadata, layer artifacts and evidence payloads when ready. Chat API is a proposal, not part of the current agreed contract.

**Sync points:**
1. Confirm Mars CRS and all coordinate meanings from the existing protocol file.
2. Agree on artifact metadata and whether GeoJSON contains longitude/latitude in the agreed Mars convention.
3. Align mock vs prototype vs observed terminology.
4. Ratify chat request/response (including route candidates, provenance, errors).
5. Wire actual backend adapters only after contract tests pass.

## 8. Testing requirements

- `npm run build` and existing lint/type-check/tests must pass.
- Unit tests: layer statuses, unavailable layer disabling, chat intent templates, candidate-route acceptance, fixture provenance.
- Integration tests: map clicks -> drawer; Start/Goal -> route API/mock -> overlay; chat context includes route id; rejection leaves current route unchanged.
- Coordinate tests: point/route/GeoJSON overlay alignment in Jezero; no implicit Earth coordinate transform.
- Failure tests: unsupported dataset, missing evidence, API unreachable, empty route, malformed geometry, null acquisition date, chat unavailable.

## 9. Codex handoff prompt

```text
Read docs/A_STELLAR_FRONTEND_IMPLEMENTATION_PLAN.md and the existing
frontend/backend protocol document. Inspect the repository before modifying
anything. Implement F2 first, then F3 and F4. Preserve the working NASA
Mars Trek OpenLayers integration and do not modify backend files. Use
reliable fixture provenance and clear synthetic-demo labels; don't invent
observed NASA measurements. Maintain the existing Mars coordinate contract.
Run frontend build and available tests, report changes and blockers.
Do not implement live A0 chat until its API is agreed with backend owners.
```

### Separate Codex prompt for chatbot sprint

```text
Implement F6 from docs/A_STELLAR_FRONTEND_IMPLEMENTATION_PLAN.md.
Create MissionAssistant UI, typed ChatRepository and MockChatRepository,
quick prompts for EXPLAIN_ROUTE, MODIFY_ROUTE, QUERY_EVIDENCE and
EXPLAIN_RISK, route context serialization, and candidate-route
Accept/Reject behavior. Use honest template-based demo answers only.
Preserve current map and /api/v1/routes/plan behavior; no backend changes
and no browser-side LLM secrets. Build and test.
```

## 10. Definition of MVP done

A-STELLAR displays real Jezero visual context with provenance, shows science/rover evidence from verifiable data or explicitly synthetic fixtures, exposes unknowns, supports route selection and demonstration route display, and offers a mocked conversational assistant that can explain limitations and preview user-requested route changes. All safety-related claims remain appropriately qualified until validated backend computations exist.
