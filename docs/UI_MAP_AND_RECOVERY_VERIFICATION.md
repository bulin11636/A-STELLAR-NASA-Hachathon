# Map layers, briefing and request recovery

The map workspace supports independent visibility and opacity controls for the
NASA global basemap, high-resolution Jezero imagery, supported DEM boundary,
initial example window, M20 DEM preview, THEMIS day/night previews, SIM 3464
geology polygons, science POIs, rover traverse, rover stops and route/mission
stops. Open **Evidence** to control them. Local raster previews are 512-pixel
visual products cropped to the DEM footprint; they do not replace native
planning data or provide calibrated temperature/risk. Geology retains its
documented approximate 100–200 m offsets. Radiation scenarios are non-spatial
and do not have a geographic heatmap.

`GET /api/v1/map/layers` advertises available local rasters and their display
extents. PNGs are generated on demand from allowlisted filenames in the
configured dataset directory. `GET /api/v1/map/geology` exposes source-backed,
simplified polygons in the map's native angular display coordinates. Missing
artifacts remain explicitly unavailable. Geology requires the optional geology
dependencies and the ignored local SIM 3464 archive:

```powershell
.\backend\.venv\Scripts\python.exe scripts\acquire_verified_products.py a4-usgs-sim3464-geology
```

The cyan outline is the supported DEM footprint. The dashed amber outline is
the initial example window, not a regional restriction. A waypoint inside that
small window cannot itself cause an outside-coverage error. Start, Goal and
every required waypoint must be inside the supported source footprint when
dynamic windowing is enabled. Frontend preflight identifies the outside stop;
the backend retains authoritative raster-coordinate validation and reports its
label and API coordinates. Map extent conversion remains enabled for visual
demo overlays without claiming independent scientific registration.

Briefing label/value pairs stack vertically so a long route ID cannot squeeze
labels into single-letter columns. Workspace tabs wrap as complete buttons.
Zoom controls sit at the map's bottom right. Computed exports distinguish
`computed_route_available` from `assessment_status`, and normalize the legacy
message that said computed map display must be disabled.

`A0_BUDGET_EXHAUSTED` identifies the application's persistent request-count or
cost-reservation ceiling, not OpenAI account credit. Its message names the
specific local setting. Changing the private `.env` requires a backend restart.
The local demo configuration was raised from 20 to 200 requests while retaining
the US$2 cost ceiling and existing accounting records. No history or reservations
are deleted and no automatic generation retry is made. After updating a limit,
use **Check chat request status**, then **Retry chat request**; recovery retains
the original request ID/settings and advances the explicit attempt version.

## Verification

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm.cmd test
npm.cmd run build
node tests/browser-ui-regressions.mjs --dataset-dir C:\Users\bulin\Downloads --python C:\A-STELLAR-NASA-Hachathon\backend\.venv\Scripts\python.exe --channel chrome
node tests/browser-workflow.mjs --dataset-dir C:\Users\bulin\Downloads --python C:\A-STELLAR-NASA-Hachathon\backend\.venv\Scripts\python.exe --channel chrome
```

The UI regression test uses the real local DEM, thermal files and geology;
NASA tile responses and all model calls are mocked. It requires the downloaded
`registration/jezero-wmts-capabilities.xml` test reference in the dataset root.
It checks independent layer controls, raster delivery and a visible DEM change,
geology polygons, bottom-right zoom placement, briefing widths at 1440/850/600px,
and explicit request recovery after increasing an exhausted limit. The original
browser workflow exercises ordered waypoint revisions, route/history reload,
pan/zoom/fullscreen preview and a crater-scale route. Neither test calls a paid
model. Reports and screenshots stay under ignored `data/processed/` directories.

Verified locally: 430 backend tests, 91 frontend tests, production build, both
browser workflows and all real local preview endpoints passed. The active
backend on port 8000 was restarted and its status confirmed the retained
20-request history, new 200-request limit and unchanged US$2 cost limit.
