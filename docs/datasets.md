# Datasets and source provenance

Scientific inputs are runtime data, not application source. Raw rasters,
download caches, local outputs and credentials are excluded from Git and the
Docker build context. Small tracked manifests, scientific records and synthetic
test fixtures remain under `data/`.

## Required terrain input

The sample planning profile uses the USGS Mars 2020 Science Investigation CTX
DEM Mosaic, `M20_JezeroCrater_CTXDEM_20m.tif`. The default profile selects a native
20 m grid and an initial 128 by 128 cell example window; dynamic regional
requests can use other supported parts of the same source. Bounds describe
coverage, not guaranteed traversability or connection between arbitrary stops.

Acquire the allowlisted product from the repository root:

```bash
python scripts/acquire_verified_products.py a1-ctx-jezero-dem-20m
```

This downloads to `data/raw/dem/` and writes source receipts. To use that location:

```bash
python scripts/run_docker.py --env-file .env --dataset-dir data/raw/dem --mode deterministic
```

An existing external directory is also supported. Pass its path to the launcher;
do not copy large inputs into tracked source. The sample profile resolves its
relative `dem` filename inside the supplied dataset root.

## Source catalog

| Source | Purpose | Important limit |
| --- | --- | --- |
| [USGS CTX DEM](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic) | Terrain grid, slope policy and native route checks | Projected distance and host-defined terrain thresholds do not certify EVA safety |
| [NASA Mars Trek](https://trek.nasa.gov/) Viking global and Jezero mosaics | Global and regional visible-light context | Image resolution/coverage differs from the DEM; demo overlays do not establish pixel registration |
| [THEMIS daytime mosaic](https://astrogeology.usgs.gov/search/map/mars_odyssey_themis_ir_day_global_mosaic_100m_v12) | Qualitative thermal-context preview | Stretched/blended visual values are not calibrated temperatures |
| [USGS SIM 3464](https://doi.org/10.3133/sim3464) | Regional geology and science context | Regional map at 1:75,000 with documented approximate 100–200 m offsets |
| [NASA M20 map exports](https://mars.nasa.gov/maps/location/api/configure/get?mission=M20) | Science locations, rover stops and traverse snapshots | Selected historical evidence does not establish complete coverage or future accessibility |
| [PDS Rover Places](https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/) | Localization and observation/clock context | Source and release identity must match the evidence profile |
| [PDS Navcam archive](https://pds-imaging.jpl.nasa.gov/beta/archive-explorer?mission=mars_2020&bundle=mars2020_navcam_ops_raw) | Bounded observation labels and browse references | A sample is not complete mission imagery |
| [Historical RAD publication](https://elib.dlr.de/106090/1/ME-SBA-2016-Reitz_MSL-RAD_ICES_2016.pdf) | Explicit dose-equivalent sensitivity scenario | Historical scenario, not a future Jezero radiation forecast |

The [acquisition manifest](../data/samples/download-manifest.json) records the
current allowlist, destinations, provider metadata and unresolved product URLs.
Some named HiRISE/CTX DEMs and the exact global nighttime THEMIS product still
have unverified download URLs. The script refuses unresolved entries rather than
substituting a similarly named raster or rendered tile. There is no supported
one-command download of every specialist's complete inputs.

## Optional acquisition

Geology archive:

```bash
python scripts/acquire_verified_products.py a4-usgs-sim3464-geology
```

The archive is stored under `data/cache/a4-geology/sim3464/`. Native browser
geology rendering additionally needs the optional geology dependencies. The
standard Docker image does not automatically include this ignored cache or every
optional geology dependency; deployment needs explicit support for those assets.

The daytime THEMIS visual product is approximately 21 GB. Download it only when
needed and after confirming storage/network capacity:

```bash
python scripts/acquire_verified_products.py a2-themis-day-global-100m-v12 --allow-large
```

Its manifest destination is `data/raw/thermal/`. The current browser raster
service looks for the expected thermal filenames beside the selected DEM; an
external dataset layout can provide that arrangement. A host-only symlink does
not make its target available inside a container; Docker needs the actual target
inside its visible mounted tree. Retain adjacent receipts when arranging data. A visual thermal preview does not by
itself configure a thermal analysis worker or establish calibrated constraints.

NASA/PDS evidence snapshots use a separate bounded acquisition command, from
`backend/` in an environment with the agentic dependencies:

```bash
python -m app.evidence.snapshots --cache-dir /absolute/path/to/dataset/evidence
```

This is an explicit network download. Observation and geology adapters can attach
additional verified reports through a trusted evidence profile; see [agents](agents.md).
The raw MSL RAD sample described in the tracked records has a labeled record-count
issue and is excluded from baseline dose assessment. Do not silently enable it.

## Dataset layout and container paths

A typical external root contains:

```text
dataset/
  M20_JezeroCrater_CTXDEM_20m.tif
  Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif  # optional
  THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018.tif  # optional, exact source required
  evidence/       # optional verified manifests and source snapshots
  registration/   # optional independent feature measurements and controls
```

The Docker launcher mounts this root read-only at `/datasets`. Evidence profiles
must reference container-visible files; a host-only absolute path is not valid
inside the container. Analysis-worker output paths must be writable and separate
from these read-only inputs.

## Units, coordinates and receipts

The inspected CTX raster uses a Mars-sphere equirectangular CRS, radius
3,396,190 m, standard parallel 18.4663 degrees and projected metre axes. A provider
summary separately lists radius 3,396,160 m; the implementation does not silently
replace the embedded CRS with that summary. The band has no embedded elevation
unit tag. Metre elevations are an explicit host interpretation backed by the
provider metadata recorded in the manifest.

The [sample profile](../data/samples/a0-planning-profile.example.json) records
these assumptions. Replacing its input requires checking source identity, CRS,
units, NoData behavior, resolution and registration rather than renaming a file.
See [map registration](map-registration.md) for wire/display conversions.

Acquisition receipts retain source/resolved URLs, byte count, SHA-256 and time.
Checksums identify local content and integrity; they are not publisher signatures
or scientific certification. Unknown source facts remain unknown. Keep raw inputs
immutable during a run and restart the backend after replacing them.

## Tracked data and credits

- `data/samples/` contains configuration examples, the acquisition manifest,
  scientific source/control records and the explicit radiation scenario.
- `data/fixtures/` contains small mock/synthetic API and planning fixtures.
  Synthetic verified-alignment fixtures cannot establish real registration.
- `data/raw/`, `data/cache/` and `data/processed/` hold ignored runtime data.

Retain NASA/JPL-Caltech, PDS and USGS product attribution and source restrictions.
[NASA media guidance](https://www.nasa.gov/nasa-brand-center/images-and-media/)
and [JPL image policy](https://www.jpl.nasa.gov/jpl-image-use-policy/) do not imply
endorsement or an unrestricted license for every product.
