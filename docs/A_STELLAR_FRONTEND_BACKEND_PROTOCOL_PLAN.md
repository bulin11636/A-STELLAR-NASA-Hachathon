# A-STELLAR — Frontend ↔ Backend Protocol & Implementation Plan

**Document status:** Proposed contract v0.1 (implement together; do not silently change fields)
**Audience:** Frontend Codex, Backend Codex, two human developers
**Scope:** F1.5 end-to-end integration of existing React/OpenLayers Mars map with Python/FastAPI. The route may initially be mocked; no real terrain safety guarantee is implied.

**Next milestone:** The user-approved [A0 API addendum](a0-api-contract.md)
extends this F1.5 baseline with computed routing and persisted metadata retrieval.
The addendum is now implemented for terrain routing and metadata retrieval;
see the [actual verification report](a0-verification-report.md). Computed browser
geometry remains guarded pending map registration. Existing fields and coordinate conventions remain authoritative.

## 0. Goal and boundaries

Deliver a working vertical slice:

1. User selects `start` and `goal` on the existing Mars map.
2. Frontend sends one JSON request to `POST /api/v1/routes/plan`.
3. Backend validates it and returns route vertices and summary fields.
4. Frontend displays the returned polyline on top of the NASA WMTS basemap, with loading, errors, and an explicit `mock` label.

**NASA map tiles (WMTS) remain browser → NASA directly**. Do **not** proxy map tiles through FastAPI unless a concrete browser/CORS constraint demands it. Backend owns computational work (future DEM, cost grids, A*, mission agent); Frontend owns map rendering and interactions. Both modules live in the same monorepo (`frontend/`, `backend/`, `docs/`).

**Not in this milestone:** A* routing, risk claims, live astronaut safety, agentic planning, DEM download, authentication, persistent missions, and automatic scientific POIs.

## 1. System interfaces

```text
Browser / React + OpenLayers
    ├── NASA Mars Trek WMTS ───────────────► NASA map tile service
    └── /api/v1/... (JSON over HTTP) ──────► Vite dev proxy ──► FastAPI :8000
                                                      │
                                                      └── mock routing; later DEM/A*
```

- **Transport:** HTTP(S), REST-style endpoints, UTF-8 JSON.
- **Request `Content-Type`:** `application/json` for POST; response JSON for success and failure.
- **Versioning:** `/api/v1`; incompatible changes require a new version or agreement between both owners.
- **Units:** distances in meters (`_m`), time in minutes (`_min`), angles in degrees; numeric fields are JSON numbers, not strings.
- **Date/time:** None required for F1.5. Add ISO 8601 UTC timestamps if future endpoints need them.
- **IDs:** `region_id` is a stable string (initially `jezero`).

### 1.1 Critical coordinate contract (agree before coding)

Mars Trek's WMTS tile matrix CRS / *native display axes* are **not automatically** the semantic latitude convention expected by a science dataset. Never treat `EPSG:4326` or a browser's Earth `fromLonLat()` helper as an authoritative Mars conversion.

The wire API is **geographic Mars coordinates**, explicitly defined for this MVP as:

| Field | Meaning |
|---|---|
| `longitude` | Degrees **east-positive**, normalized to **[0, 360)**. |
| `latitude` | Degrees **planetocentric**, in **[-90, 90]**. |
| `coordinate_system` | Exact protocol constant `MARS_2000_PLANETOCENTRIC_EAST_360_V1`. This is an **application convention**, not a registered EPSG CRS. |
| Array ordering | Not applicable: **named fields** are mandatory; do not send bare `[x,y]` pairs on wire. |

**Before actual georeferenced plotting:** Frontend and backend owners must verify the currently loaded NASA layer's declared CRS, east/west longitude domain, latitude convention, raster metadata, and any planetographic↔planetocentric conversion. Implement this as a single explicit conversion adapter at the OpenLayers boundary, not scattered UI math. A screenshot showing X/Y degrees does **not** prove the latitude convention. If this conversion remains unverified, use the mock route for integration only, flag the display `coordinate convention not validated`, and do not claim geospatial accuracy.

Recommended module ownership:
- Frontend `src/geo/marsCoordinates.ts`: `mapViewToApiCoordinate()` and `apiCoordinateToMapView()`; tests with known fixtures.
- Backend `app/geo/coordinates.py`: check wire convention and later convert to local DEM raster row/col using dataset-specific transforms.
- Shared test fixture(s) in `data/fixtures/`: same known Mars coordinate expected on both sides.

## 2. Canonical API contracts

### 2.1 `GET /api/v1/health`

**200 OK**

```json
{
  "status": "ok",
  "service": "a-stellar-backend",
  "api_version": "v1"
}
```

Frontend may use it to show whether the API is reachable; do not poll aggressively. Network or 5xx failure means backend unavailable.

### 2.2 `GET /api/v1/regions`

A minimal region list for future ROI selection. This can be implemented alongside mock routing or in the next sprint; do not block first route integration on it.

**200 OK**

```json
{
  "regions": [
    {
      "id": "jezero",
      "name": "Jezero Crater",
      "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
      "routing_available": true,
      "routing_mode": "mock"
    }
  ]
}
```

`routing_available=true` means *the demo endpoint accepts requests*, **not** that terrain-aware planning is available. Region bounding polygons, science points, and raster metadata can be added later without altering existing fields.

### 2.3 `POST /api/v1/routes/plan` — required

**Request JSON**

```json
{
  "region_id": "jezero",
  "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  "start": { "longitude": 77.42, "latitude": 18.44 },
  "goal": { "longitude": 77.48, "latitude": 18.46 },
  "mode": "safest"
}
```

**Schema / validation**

- `region_id`: required string; for F1.5 only `jezero` supported.
- `coordinate_system`: required exact constant; mismatches are errors, never guessed/transformed silently.
- `start`, `goal`: required objects with both numeric fields; require **finite** numbers, `0 <= longitude < 360`, `-90 <= latitude <= 90`.
- `mode`: enum `shortest | safest`; both modes may produce the same mock geometry but must be explicitly labeled mock.
- If start equals goal: return a useful `400` error (or support a one-point route consistently, but choose one behavior and test it). This specification chooses `400`.
- Do not clamp invalid coordinates or substitute defaults silently.

**200 OK — mock example**

```json
{
  "status": "success",
  "route_id": "demo-jezero-001",
  "region_id": "jezero",
  "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  "mode": "safest",
  "source": "mock",
  "route": [
    { "longitude": 77.42, "latitude": 18.44 },
    { "longitude": 77.45, "latitude": 18.45 },
    { "longitude": 77.48, "latitude": 18.46 }
  ],
  "metrics": {
    "distance_m": null,
    "estimated_time_min": null,
    "risk_score": null
  },
  "warnings": ["Demonstration route only. No terrain or astronaut safety evaluation performed."]
}
```

**Meaning of fields**

| Field | Rule |
|---|---|
| `status` | Literal `success` on HTTP 200. |
| `route_id` | Opaque non-empty string, unique where practical. |
| `source` | `mock | computed` (render obvious MOCK badge when mock). |
| `route` | Ordered polyline vertices, including request start and goal; minimum 2 points. |
| `metrics.distance_m` | Computed distance in meters, or `null` when unknown. Never use invented `0`. |
| `metrics.estimated_time_min` | Estimated movement time, or `null` when unknown; later document walking speed assumptions. |
| `metrics.risk_score` | Normalized `[0,1]` only **if a defined model actually computes it**; otherwise `null`. |
| `warnings` | Array of plain-language caveats; always nonempty for mocked routes. |

The sample intermediate vertex and ID are illustrative; implementation may use a direct 2-point line for its initial mock. Do not fabricate NASA-derived values. For computed routes, backend must attach dataset provenance and risk-model documentation before exposing `source: "computed"` as an operationally meaningful result.

### 2.4 Error envelope — all endpoints

**JSON for 400 / 404 / 422 / 500**

```json
{
  "error": {
    "code": "UNSUPPORTED_COORDINATE_SYSTEM",
    "message": "The requested Mars coordinate convention is not supported.",
    "details": null
  }
}
```

Expected errors:

| HTTP | `code` | When |
|---|---|---|
| 400 | `INVALID_ROUTE` | Start equals goal or semantic route error. |
| 400 | `UNSUPPORTED_COORDINATE_SYSTEM` | CRS convention is not exact expected value. |
| 404 | `UNKNOWN_REGION` | `region_id` not supported. |
| 422 | `VALIDATION_ERROR` | Missing/invalid fields, nonfinite coordinates, invalid mode or range. |
| 500 | `INTERNAL_ERROR` | Unexpected backend failure; do not expose stack traces or secrets to client. |

FastAPI's default 422 format differs: register an exception handler to standardize validation responses, or explicitly document and implement a compatible frontend handler. **For this contract, standardize to the envelope above.** In production include an optional correlation ID; do not leak exception tracebacks.

## 3. Repo paths and implementation steps

```text
A-STELLAR/
├── frontend/
│   ├── src/
│   │   ├── geo/marsCoordinates.ts       # Boundary conversion; explicit validation
│   │   ├── services/apiClient.ts        # fetch + structured errors
│   │   ├── services/routes.ts           # typed planRoute()
│   │   ├── types/api.ts                 # DTOs / enums
│   │   └── ... existing MarsMap ...     # route vector layer; map interaction
│   └── vite.config.ts                   # /api proxy to backend
├── backend/
│   ├── app/main.py                      # FastAPI app + routers
│   ├── app/api/routes.py                # health, regions, routes/plan
│   ├── app/models.py                    # Pydantic input/output schemas
│   ├── app/geo/coordinates.py           # validate convention / future transforms
│   └── tests/test_contract.py           # request/response tests
├── data/fixtures/                    # shared known-coordinate fixtures
└── docs/
    └── A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md
```

### Step A — Both developers: freeze shared decisions

1. Commit this file under `docs/` and agree on endpoint names, field names, coordinate system constant, and error envelope.
2. Verify what latitude convention NASA WMTS and the chosen DEM truly use. Document evidence and any required conversion. Do **not** assume metadata labels alone fully describe it.
3. Agree which layer is authoritative for conversion (`map view ↔ wire` on frontend; `wire ↔ DEM` on backend).

### Step B — Backend owner (can proceed without frontend)

1. Scaffold FastAPI app in `backend/` and add `GET /api/v1/health`.
2. Add Pydantic models and `POST /api/v1/routes/plan`; validate fields and return mock path with `source: "mock"`, `null` metrics and warning.
3. Add consistent error handling and optionally `GET /api/v1/regions`.
4. Publish OpenAPI docs at `/docs` and schema at `/openapi.json` (FastAPI defaults).
5. Write API tests for success, unknown region, wrong CRS, invalid coordinate, invalid mode, and same start/goal.
6. Do not implement terrain risk in the mock and do not report fake quantitative safety metrics.

### Step C — Frontend owner (can proceed with fixtures/mock)

1. Keep NASA WMTS in the current OpenLayers map; no NASA tiles through `/api`.
2. Add strongly typed API DTOs matching this file; create one `fetch` wrapper that parses success/error and handles network timeouts/failures appropriately.
3. Add Vite dev proxy to backend (sample below).
4. Add `Start` and `Goal` pick modes and a `Plan Route` action; show selected coordinates.
5. Translate map coordinates into the **verified** wire convention using `marsCoordinates.ts`; do not use Earth CRS helpers.
6. Render response `route` in a dedicated OpenLayers vector layer; preserve NASA raster layers unchanged.
7. Show `source: mock` and warnings clearly. Display missing metrics as `—` rather than `0`.
8. Handle request states: idle → loading → success/error. Disable duplicate submissions and clear stale routes when start or goal changes.

**Vite dev proxy snippet** (merge with current config):

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  }
});
```

Frontend calls **relative** `/api/v1/...`, never hardcoded localhost in component logic. For deployment configure a same-origin reverse proxy or environment-specific API base URL; configure FastAPI CORS only if browser truly calls a separate origin.

### Step D — Integration together

1. Backend: `cd backend && python -m uvicorn app.main:app --reload --port 8000` (after dependencies installed).
2. Frontend: `cd frontend && npm install && npm run dev`.
3. Test API `GET /api/v1/health` through the frontend origin, e.g. `http://localhost:5173/api/v1/health`.
4. Click two distinct Jezero points; send request; inspect Network tab and server logs.
5. Verify coordinate conversion, returned polyline on top of NASA imagery, and explicit mock labeling.
6. Change zoom/pan and verify route stays attached to its surface coordinates.
7. Simulate backend offline and invalid input; verify useful UI error messages and no silent false successes.

## 4. Tests and acceptance criteria

### Contract tests (backend)

- Health returns stable JSON fields and 200.
- Valid route POST returns status 200, all mandatory fields, 2+ finite coordinate vertices; first/last match request.
- Metrics for mock routes are `null`; warning is present.
- Bad CRS → 400 with `UNSUPPORTED_COORDINATE_SYSTEM`.
- Unknown region → 404 with `UNKNOWN_REGION`.
- Missing fields, invalid lat/lon, string/NaN/infinite values, bad mode → 422 `VALIDATION_ERROR`.
- Same start & goal → 400 `INVALID_ROUTE`.
- Every error is `{"error":{"code":...,"message":...,"details":...}}`.

### UI acceptance (frontend)

- Existing NASA MOLA WMTS map still loads unaffected.
- User can choose Start and Goal and see the positions/coordinate labels.
- Clicking `Plan Route` makes exactly one POST to `/api/v1/routes/plan`.
- Route returned by backend is visible over map and remains registered when panning/zooming.
- `MOCK / NOT SAFETY-VALIDATED` is visible for mocked routes; missing metrics are shown as unknown.
- Loading, validation, server error, and network offline states are explicit.
- No use of `EPSG:4326` or `fromLonLat` as a shortcut for Mars without documented conversion and tests.

### Definition of done (F1.5)

- Both services start locally; one end-to-end request succeeds.
- Contract tests pass; frontend build passes (`npm run build`).
- At least one shared real-world Jezero coordinate fixture validates map → API → map round-trip **after confirming the source CRS metadata**.
- Known coordinate uncertainty is documented rather than represented as solved.
- Docs show how two contributors run the project.

## 5. Next protocol additions (do NOT implement yet)

- `GET /api/v1/regions/{id}/metadata` — DEM extent, resolution, science layers, provenance, coordinate transformation metadata.
- `GET /api/v1/regions/{id}/science-pois` — science targets and provenance.
- `POST /api/v1/routes/plan` with route constraints (max slope, return time, cost weights), once validated.
- `POST /api/v1/missions/plan` — Agentic orchestration, requiring tool-validation and human approval for safety-related outputs.
- Optional route GeoJSON export **only after explicitly defining Mars CRS semantics**; default GeoJSON typically assumes Earth WGS84 and is unsuitable without an agreed nonstandard extension.

## 6. Codex handoff prompts

**Frontend Codex**

> Read `docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md` and implement only the Frontend Owner tasks for F1.5 in the existing React/OpenLayers app. Preserve the working NASA Mars Trek WMTS layer. Add typed `/api/v1` client, start/goal selection, route vector overlay, mock disclaimers, and error/loading states. Follow the coordinate-convention caveats; do not assume Earth projection. Build and report what was verified versus blocked.

**Backend Codex**

> Read `docs/A_STELLAR_FRONTEND_BACKEND_PROTOCOL_PLAN.md` and implement only the Backend Owner tasks for F1.5 using FastAPI/Pydantic. Match the request/response/error JSON contract exactly, document the coordinate system constant, return explicit mocked routes with null metrics, and add automated contract tests. Do not claim the stub performs actual terrain-aware routing.

**Integration Codex / human**

> Run both apps locally and execute Step D and Section 4 acceptance criteria. Confirm map↔wire coordinate semantics with NASA/DEM metadata before declaring geospatial accuracy. List any deviations and fix them or propose a versioned contract change.

---

**Design rule:** Treat the route protocol as an interface between a geospatial *viewer* and a planning *service*. Preserve data provenance, refuse implicit CRS assumptions, and never portray unverified demo paths as astronaut-safe.
