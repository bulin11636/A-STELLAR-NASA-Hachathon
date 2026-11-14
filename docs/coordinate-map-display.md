# Coordinate and map-display boundary

Status: a CRS conversion adapter is implemented and unit-tested; NASA WMTS to
local-DEM pixel registration is still unverified. This is a display/protocol
note, not route or astronaut-safety validation.

## Two coordinate representations

The public route API uses
`MARS_2000_PLANETOCENTRIC_EAST_360_V1`: east-positive longitude in `[0, 360)`
and planetocentric latitude. The local CTX planning raster uses the Mars sphere
with radius 3,396,190 m, so its spherical latitude agrees with that wire
convention.

The Mars Trek MOLA WMTS layer advertises
`urn:ogc:def:crs:EPSG::104905`. The corresponding Mars 2000 ESRI definition
(`ESRI:104905`) is an ellipsoidal geographic CRS with semi-major axis
3,396,190 m and inverse flattening 169.894447223612. Its native latitude is
planetographic. The service capabilities remain the authoritative source for
the selected layer, matrix grid, extent, and advertised service identifier:

<https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml>

## Implemented adapter

`frontend/src/geo/marsCoordinates.ts` converts latitude explicitly. With
`a = 3396190` and `b = a * (1 - 1 / 169.894447223612)`:

```text
planetographic = atan((a² / b²) * tan(planetocentric))
planetocentric = atan((b² / a²) * tan(planetographic))
```

Longitude is unchanged apart from the UI's `[-180, 180]` display seam. The
adapter is used for map clicks, selected endpoint markers, and the small
PDS-derived evidence fixture. The legacy fixture-only mode remains available
for existing mock tests.

For the published Jezero example, API latitude `18.4446°` becomes WMTS display
latitude approximately `18.648595°`; this is why direct latitude pass-through
was incorrect.

## Remaining gate

The adapter only proves the stated datum conversion. It does not establish
that a particular NASA rendered tile, the WMTS matrix origin, and the CTX DEM
are pixel-registered at a justified tolerance. `MAP_REGISTRATION_VALIDATED`
therefore remains `false`, and a computed route polyline is not drawn over
NASA imagery. Mock routes remain labeled mock. No map state represents a
validated route or astronaut-safety finding.

To lift the gate, retain reproducible NASA WMTS, PDS wire-coordinate, and DEM
control records; compare at least independent control points under a documented
tolerance; record browser tile behavior; and add a browser-level acceptance
test before changing the gate.
