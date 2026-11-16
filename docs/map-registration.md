# Map coordinates and independent registration

The UI currently draws computed routes over NASA imagery as **visual demo
overlays** after coordinate conversion. It does not require independent pixel
registration to show the line. `map_alignment` remains separate provenance;
visibility must not be presented as proof of alignment or astronaut suitability.

## Wire, source and display coordinates

The public wire convention is `MARS_2000_PLANETOCENTRIC_EAST_360_V1`: east-positive
longitude in `[0,360)` and planetocentric latitude in `[-90,90]`. The inspected CTX
planning raster uses the Mars sphere, radius 3,396,190 m, in a projected
metric equirectangular grid.

The NASA WMTS layer identifier uses `urn:ogc:def:crs:EPSG::104905`, corresponding
to the Mars 2000 ellipsoidal geographic definition `ESRI:104905`. The implemented
display adapter treats its latitude as planetographic, with semi-major axis
3,396,190 m and inverse flattening 169.894447223612. With `b = a * (1 - 1/f_inv)`:

```text
planetographic = atan((a^2 / b^2) * tan(planetocentric))
planetocentric = atan((b^2 / a^2) * tan(planetographic))
```

Longitude is normalized at the display seam. The code is in
`frontend/src/geo/marsCoordinates.ts`. This mathematical adapter does not itself
establish the pixel semantics or registration of any particular rendered tile.
Layer capabilities, source records and independent measurements remain necessary.

The global background is Viking visible-light imagery; the local Jezero
HiRISE/CTX/HRSC mosaic is a separate layer. The planning profile explicitly names
the target WMTS layer for registration. Image resolution and displayed zoom do
not determine the native DEM resolution used by A*.

## Collect independent controls

For an independently verified registration outcome, record at least four
spatially separated, identifiable terrain features. Each observation needs:

- API wire coordinate and its uncertainty.
- Exact DEM pixel coordinate.
- Independently picked NASA WMTS coordinate.
- WMTS matrix identifier and measured pixel resolution.
- Feature-picking uncertainty and source evidence.

Do not derive every coordinate from the same transform and call the round trip
an independent measurement. Preserve the original assets, source identity and
measurement method. Controls must cover the intended route, not merely one corner
of the DEM.

## Evidence package

Keep small immutable evidence files inside the configured dataset directory:

```text
registration/
  jezero-wmts-capabilities.xml
  jezero-independent-measurements.json
  jezero-controls.json
```

Reference the control JSON through `registration_controls` in the planning
profile. The control schema is `ControlSet` in
`backend/app/planning/registration.py`. Its shape includes:

```json
{
  "schema_version": "1",
  "data_kind": "observed",
  "measurement_method": "independent_feature_measurement",
  "source_sha256": "<exact DEM SHA-256>",
  "wmts_layer": "NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018",
  "wmts_matrix_set": "default028mm",
  "wmts_crs": "urn:ogc:def:crs:EPSG::104905",
  "latitude_type": "planetographic",
  "semi_major_m": 3396190.0,
  "inverse_flattening": 169.894447223612,
  "capabilities_file": "jezero-wmts-capabilities.xml",
  "capabilities_sha256": "<SHA-256>",
  "measurement_file": "jezero-independent-measurements.json",
  "measurement_sha256": "<SHA-256>",
  "observations": []
}
```

This is a schema illustration, not valid completed evidence. Empty observations
and placeholder hashes cannot establish verification. Hash assets after capture.

## QGIS visual reference

A saved capabilities XML is metadata, not an image that can be dragged onto a
QGIS canvas. Create a bounded georeferenced Jezero preview alongside the DEM:

```bash
python scripts/download_jezero_wmts_preview.py \
  --dem /path/to/dataset/M20_JezeroCrater_CTXDEM_20m.tif \
  --output /path/to/dataset/registration/jezero-wmts-preview-z11.tif \
  --capabilities-output /path/to/dataset/registration/jezero-wmts-capabilities.xml \
  --zoom 11
```

This command downloads NASA data and writes local files. The preview covers the
intersection of the advertised mosaic and DEM and uses the WMTS display CRS.
It is a feature-picking reference, not registration proof by itself.

## Verify route applicability

From the repository root:

```bash
python scripts/verify_registration.py \
  --dataset-dir /path/to/dataset \
  --controls /path/to/dataset/registration/jezero-controls.json \
  --request-file /path/to/route-request.json
```

The request file follows [PlanRouteRequest](api.md#plan-inputs). Without a route,
the verifier cannot establish route-wide applicability. It checks source and
asset hashes, layer/CRS identity, bounded residuals, spread of controls and route
containment in their hull. Failed/incomplete evidence stays unverified with
reasons; the script exits with status 2 for an unverified outcome.

Synthetic controls can exercise the verifier in isolated tests but cannot certify
real NASA/DEM alignment. A verified map-registration result is also not a calibrated
terrain/environment model or authorization to execute an astronaut mission.
