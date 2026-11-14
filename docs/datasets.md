# Data locations and sources

Repository-managed scientific artifacts and test fixtures belong under `data/`.
For the approved [A0 milestone](a0-implementation-plan.md#local-input-policy),
the user's large raw rasters remain at `~/nasa/project/dataset` and are read
through explicit local configuration. Do not copy or move them merely to match
the repository defaults. Generated grids, receipts and route records stay in
ignored `data/` output folders. Existing worker defaults below remain unchanged
until the milestone's configuration support is implemented.

```text
data/
  raw/
    dem/        A1 GeoTIFF inputs (ignored)
    thermal/    A2 GeoTIFF inputs (ignored)
  cache/        Downloaded NASA/PDS/USGS products and source receipts (ignored)
  processed/    Generated grids and scientific reports (ignored)
  fixtures/     Small shared coordinate and API test fixtures (tracked)
  samples/      Small provenance records and explicit scenario configs (tracked)
```

The existing caches and generated reports are preserved at their original paths. No large products were moved or redownloaded. `.gitkeep` files establish empty raw-input folders; do not commit scientific GeoTIFFs. Synthetic fixtures are not observations.

## A1/A2 GeoTIFF inputs

| Destination under `data/raw/` | Filename |
| --- | --- |
| `dem/` | `M20_JezeroCrater_CTXDEM_20m.tif` |
| `dem/` | `NES_JEZ_MID_DEM_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018.tif` |
| `dem/` | `JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif` |
| `thermal/` | `Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif` |
| `thermal/` | `THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018.tif` |

These filenames come from Sam's standalone-agent handoff; availability, calibration, CRS, pixel resolution and claimed leveling improvements require product-level verification. Names alone do not establish production readiness. A1 defaults to the CTX DEM and writes grids to `data/processed/a1/`; A2 defaults to the two thermal mosaics. Default paths are independent of the launch directory. Explicit CLI input paths remain supported.

## A3/A4/A6 sources

| Source | Local storage / purpose | Verification and limits |
| --- | --- | --- |
| [NASA M20 map configuration](https://mars.nasa.gov/maps/location/api/configure/get?mission=M20) and linked vector exports | `cache/evidence/`; sampling sites, rover stops and traverse | SHA-256 snapshots; accepted angular/projected fields checked against PDS controls. These are mission-map exports, not direct Mars Trek geology layers. |
| [PDS PLACES](https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/) | `cache/evidence/` and `cache/a6-observations/`; localization, exposures and clock ranges | Release identity, labeled fields/units/counts and receipts checked. Does not establish WMTS/DEM registration. |
| [USGS SIM 3464](https://doi.org/10.3133/sim3464) | `cache/a4-geology/sim3464/`; regional geology | Archive CRC/SHA-256, native CRS and vector checks; approximate 100–200 m basemap offsets remain relevant. |
| [PDS Atlas Navcam](https://pds-imaging.jpl.nasa.gov/beta/archive-explorer?mission=mars_2020&bundle=mars2020_navcam_ops_raw) | `cache/a6-observations/`; labels and browse images | Eight bounded products verified; complete mission image coverage and Mastcam-Z reconciliation are not established. |
| [MSL RAD RDR](https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/) | `cache/a3-radiation/msl-rad-rdr/`; absorbed-dose inspection | Historical Gale Crater detector rates, not Jezero dose equivalent. Saved sample has a labeled record-count discrepancy and is excluded from baseline use. |
| [RAD team publication](https://elib.dlr.de/106090/1/ME-SBA-2016-Reitz_MSL-RAD_ICES_2016.pdf) | `samples/msl-rad-literature-scenario.json` | Explicit historical dose-equivalent replay; no calibrated future Jezero prediction. |

## Provenance and fixtures

Downloads retain original URLs, local SHA-256/size receipts and retrieval times. Checksums identify local content/version integrity, not provider-signed authenticity. Processed artifacts retain source IDs, coordinate/coverage assumptions, processing versions and exclusions. Unknown values remain unknown.

## Verified acquisition manifest

`data/samples/download-manifest.json` is the tracked allowlist for raster acquisition. `scripts/acquire_verified_products.py` streams each eligible product to its ignored `data/raw/` destination and writes an ignored source receipt under `data/cache/source-receipts/` with the original/resolved URL, UTC retrieval time, byte count and SHA-256. It refuses products whose URLs have not been verified and requires `--allow-large` for a manifest entry marked large.

The currently verified A1 input is the 87 MB USGS **Mars 2020 Science Investigation CTX DEM Mosaic**, `a1-ctx-jezero-dem-20m`. The verified A2 candidate is the 21 GB USGS **Mars Odyssey THEMIS-IR Day Global Mosaic 100m v12**, `a2-themis-day-global-100m-v12`. Its provider documents 8-bit stretch/blend visual values, not calibrated temperature units, so it remains a **prototype-only** A2 input. Obtain approval before invoking the latter:

```powershell
python scripts/acquire_verified_products.py a1-ctx-jezero-dem-20m
# only after explicit approval for the 21 GB product:
python scripts/acquire_verified_products.py a2-themis-day-global-100m-v12 --allow-large
```

The two HiRISE/CTX/HRSC DEM filenames and the named global THEMIS-night file remain **unverified URL gaps** in the manifest. A USGS regional night mosaic or a map tile is not a silent replacement.

`data/samples/` contains the vector, geology, A6 and RAD verification records plus the radiation scenario. `data/fixtures/` contains the mock coordinate fixture, factual PDS control fixture and route-request fixture. Mock coordinate arithmetic does not certify scientific alignment.

`a0-mission.json`, `a0-profile.json` and `a0-script.json` are tracked A0 demonstration inputs. The script is an offline decision replay, not model output or scientific evidence. Per-run A0 reports and raw-result artifacts live in ignored `data/processed/a0/`; its runtime SKILL.md is a packaged application instruction asset under `backend/app/coordinator/skills/`, not a dataset.

Retain NASA/JPL/PDS/USGS credits and product-specific restrictions. General [NASA usage guidance](https://www.nasa.gov/nasa-brand-center/images-and-media/) and [JPL image policy](https://www.jpl.nasa.gov/jpl-image-use-policy/) do not imply an unrestricted license or endorsement. No raw imagery is shipped in the repository.

Commands and measured results are in [Agents](agents.md).

## Verified local planning window

The [portable profile](../data/samples/a0-planning-profile.example.json) selects
CTX source window `[1210,2440,128,128]` (column, row, width, height), plus a
one-pixel derivative halo. It retains the native 20 × 20 m grid, sphere radius
3,396,190 m, standard parallel 18.4663°, zero prime/central meridians and metre
axes. No reprojection or upsampling occurs. The embedded CRS is authoritative
for this run; the acquisition manifest's provider-summary radius 3,396,160 m
is a documented discrepancy, not substituted into the transform. A PDS control
agrees in projected coordinates to 0.0000253 m, but does not prove feature
alignment to NASA imagery.

The band has no unit tag. Metre elevations are an explicit host interpretation
supported by the CTX provider metadata recorded in the acquisition manifest;
the local file has no publisher/acquisition receipt. Metadata therefore retains
local identity, SHA-256 and null unknown source facts. Distances and slope
derivatives use native projected metres, with projection distortion retained.
This is a research policy, not a calibrated physical safety model.

All five supplied rasters were inventoried through headers. Other DEMs were
not selected because their source identity/units require further verification.
The THEMIS day visual mosaic remains unsuitable for calibrated temperatures.
The latest [run report](a0-verification-report.md) records optional receipts and
the RAD quality exclusion; none supplies a route constraint by default.
