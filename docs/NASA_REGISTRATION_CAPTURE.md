# Real NASA map registration capture

The application deliberately starts with `map_alignment: unverified`. The
Jezero HiRISE / CTX / HRSC NASA WMTS mosaic is a suitable visual reference for
the local 20 m CTX DEM, but choosing that layer does **not** establish that
the imagery, API wire coordinates, and DEM pixels coincide.

## What to capture

Before a production route can be drawn over NASA imagery, an operator must
collect at least four spatially separated, clearly identifiable terrain
features. Each observation must independently record:

- the API wire coordinate (Mars 2000, planetocentric, east-positive),
- the exact DEM pixel coordinate,
- the NASA WMTS coordinate read from the NASA layer,
- the WMTS matrix identifier and measured pixel resolution,
- bounded wire and feature-picking uncertainty.

Use stable features such as crater rims or intersections of unambiguous
surface features. Do not derive all three coordinates from the same transform
or use an automatic round trip as a measurement.

## Evidence package location

Store the following small immutable evidence files inside the configured
`A_STELLAR_DATASET_DIR` (normally the Downloads directory), then reference the
control JSON from `registration_controls` in the planning profile:

```text
registration/
  jezero-wmts-capabilities.xml
  jezero-independent-measurements.json
  jezero-controls.json
```

`jezero-controls.json` must follow this schema shape. Hash every evidence file
after capture; do not copy placeholder hashes into production.

```json
{
  "schema_version": "1",
  "data_kind": "observed",
  "measurement_method": "independent_feature_measurement",
  "source_sha256": "<sha256 of the exact DEM file>",
  "wmts_layer": "NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018",
  "wmts_matrix_set": "default028mm",
  "wmts_crs": "urn:ogc:def:crs:EPSG::104905",
  "latitude_type": "planetographic",
  "semi_major_m": 3396190.0,
  "inverse_flattening": 169.894447223612,
  "capabilities_file": "jezero-wmts-capabilities.xml",
  "capabilities_sha256": "<sha256>",
  "measurement_file": "jezero-independent-measurements.json",
  "measurement_sha256": "<sha256>",
  "observations": []
}
```

The application accepts a production `verified` outcome only when all controls
pass the bounded DEM/WMTS tolerance, are spatially spread, and the entire
route lies inside their control hull. A failed or incomplete package remains
pending and never enables the map route overlay.

## Run the verifier

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_registration.py --dataset-dir C:\Users\<you>\Downloads
```

Review the JSON output. Only `map_alignment: verified` for the planned route
is eligible to display computed geometry on the NASA map.
