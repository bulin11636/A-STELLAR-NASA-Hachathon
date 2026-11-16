import type { EvidenceLayer, EvidenceState } from "../types/evidence.ts";
import { CATALOG_URL, JEZERO_LAYER_ID, NASA_CRS } from "./marsWmts.ts";

const BASE_LAYERS: readonly EvidenceLayer[] = [
  {
    id: "mars_basemap",
    label: "Global Mars terrain (MOLA)",
    family: "Global terrain background",
    state: "observed",
    validationStatus: "validated_for_demo",
    renderable: true,
    provenance: {
      sourceName: "NASA Mars Trek — MGS MOLA global color hillshade",
      sourceUrl: CATALOG_URL,
      origin: "official_source",
      observationDate: null,
      publicationDate: null,
      ingestionDate: null,
      resolution: "463 m/pixel",
      units: "Colorized topography; not natural-color imagery",
      coordinateSystem: NASA_CRS,
      limitations: ["Visual context only. NASA WMTS latitude convention has not been validated against the application wire convention or the local DEM."],
    },
  },
  {
    id: "jezero_imagery",
    label: "High-resolution Jezero imagery",
    family: "Optical / context",
    state: "observed",
    validationStatus: "not_validated",
    renderable: true,
    provenance: {
      sourceName: "NASA Mars Trek — Jezero HiRISE / CTX / HRSC mosaic",
      sourceUrl: CATALOG_URL,
      origin: "official_source",
      observationDate: null,
      publicationDate: null,
      ingestionDate: null,
      resolution: "NASA WMTS Jezero mosaic",
      units: "Visual context; not a verified route-registration surface",
      coordinateSystem: NASA_CRS,
      limitations: [`${JEZERO_LAYER_ID} covers Jezero only. Routes use the M20 DEM coordinate conversion for a visual demo overlay.`],
    },
  },
  {
    id: "jezero_dem",
    label: "Jezero DEM coverage",
    family: "Topographic",
    state: "prototype",
    validationStatus: "not_validated",
    renderable: true,
    provenance: {
      sourceName: "USGS Mars 2020 Science Investigation CTX DEM Mosaic",
      sourceUrl: "https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic",
      origin: "official_source",
      observationDate: null,
      publicationDate: "2021-10-14",
      ingestionDate: null,
      resolution: "20 m/pixel",
      units: "Provider metadata describes vertical coordinates in metres; embedded GeoTIFF band unit is absent",
      coordinateSystem: "Mars-2000 sphere Equirectangular; local raster/wire alignment not validated",
      limitations: ["Cyan outline shows the supported DEM footprint, not individual NoData cells or safe terrain. The small example window does not limit regional routing."],
    },
  },
  {
    id: "geology",
    label: "SIM 3464 geology",
    family: "Geology / science",
    state: "observed",
    validationStatus: "not_validated",
    renderable: false,
    provenance: {
      sourceName: "USGS Scientific Investigations Map 3464",
      sourceUrl: "https://doi.org/10.3133/sim3464",
      origin: "official_source",
      observationDate: null,
      publicationDate: "2020-12-02",
      ingestionDate: null,
      resolution: "Regional geologic map, 1:75,000",
      units: "Projected geometry axes in metres after archive CRS validation",
      coordinateSystem: "Mars-sphere Transverse Mercator; raster/wire alignment not validated",
      limitations: ["Regional SIM 3464 polygons are loaded from the local archive when available, simplified to 20 m for display. Source reports approximate 100–200 m offsets. Science POIs have a separate toggle."],
    },
  },
  {
    id: "science_pois",
    label: "Perseverance science POIs",
    family: "Science context",
    state: "observed",
    validationStatus: "not_validated",
    renderable: true,
    provenance: {
      sourceName: "NASA M20 documented sample-site export",
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_SAMPLE_v3.json",
      origin: "official_source",
      observationDate: null,
      publicationDate: null,
      ingestionDate: "2026-11-14",
      resolution: null,
      units: "Named Mars longitude/latitude source records",
      coordinateSystem: "MARS_2000_PLANETOCENTRIC_EAST_360_V1; WMTS map alignment not validated",
      limitations: ["The browser overlay is a small selected fixture, not the full source export. Historical science context does not infer future sampling priority."],
    },
  },
  {
    id: "rover_history",
    label: "Perseverance traverse",
    family: "Historical rover observations",
    state: "observed",
    validationStatus: "not_validated",
    renderable: true,
    provenance: {
      sourceName: "NASA M20 map exports and PDS Mars 2020 Rover Places",
      sourceUrl: "https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/",
      origin: "official_source",
      observationDate: null,
      publicationDate: null,
      ingestionDate: null,
      resolution: null,
      units: "Location coordinates and spacecraft-clock observations",
      coordinateSystem: "Source records retain documented Mars coordinate fields; map alignment not validated",
      limitations: ["Historical rover traversal is not astronaut-safety evidence. The current browser overlay is a small selected fixture, not complete mission coverage."],
    },
  },
  {
    id: "thermal",
    label: "THEMIS daytime visual context",
    family: "Thermal",
    state: "prototype",
    validationStatus: "not_validated",
    renderable: false,
    provenance: {
      sourceName: "Local THEMIS visual mosaic preview",
      sourceUrl: "https://astrogeology.usgs.gov/search/map/mars_odyssey_themis_ir_day_global_mosaic_100m_v12",
      origin: "official_source",
      observationDate: null,
      publicationDate: null,
      ingestionDate: null,
      resolution: "100 m/pixel source, downsampled preview",
      units: "Candidate daytime mosaic values are qualitative visual values, not calibrated temperatures",
      coordinateSystem: "Candidate product: Simple Cylindrical, planetocentric, east-positive",
      limitations: ["Preview availability is checked against the backend dataset directory. Contrast-stretched visual values are not calibrated temperatures or thermal risk."],
    },
  },
] as const;

const visualLayer=(id:string,label:string,source:EvidenceLayer,limitations:readonly string[]):EvidenceLayer=>({
  ...source,id,label,renderable:true,provenance:{...source.provenance,limitations},
});
const ALL_LAYERS: readonly EvidenceLayer[] = [
  ...BASE_LAYERS,
  visualLayer('rover_stops','Perseverance stops & Navcam references',BASE_LAYERS.find(l=>l.id==='rover_history')!,['Selected historical rover stops and image references. Independently toggled from science POIs and traverse lines.']),
  visualLayer('route','Route & mission stops',BASE_LAYERS.find(l=>l.id==='jezero_dem')!,['Computed or mock route and selected mission stops. Visual demo overlay.']),
  visualLayer('planning_window','Initial DEM example window',BASE_LAYERS.find(l=>l.id==='jezero_dem')!,['Dashed amber outline is the initial example window. Dynamic regional routes may extend beyond it within the supported DEM footprint.']),
  visualLayer('dem_surface','M20 DEM elevation preview',BASE_LAYERS.find(l=>l.id==='jezero_dem')!,['Local DEM downsampled and contrast-stretched for display. Does not replace native-resolution route checks.']),
  {...visualLayer('thermal_night','THEMIS nighttime visual context',BASE_LAYERS.find(l=>l.id==='thermal')!,['Local nighttime raster cropped to the DEM footprint. Visual values are not calibrated temperature or risk.']),
    provenance:{...BASE_LAYERS.find(l=>l.id==='thermal')!.provenance,sourceName:'Local THEMIS nighttime visual mosaic',sourceUrl:CATALOG_URL,
      limitations:['Local nighttime raster identity is not provider-verified. Visual context only; no calibrated temperature or risk.']}},
];

export const LAYER_GROUPS = [
  {label:'Basemaps',ids:['mars_basemap','jezero_imagery']},
  {label:'A1 — Terrain & traversability (includes A5)',ids:['jezero_dem','dem_surface','planning_window']},
  {label:'A2 — Thermal context',ids:['thermal','thermal_night']},
  {label:'A4 — Geology & science',ids:['geology','science_pois']},
  {label:'A6 — Rover observations',ids:['rover_history','rover_stops']},
  {label:'Mission route & stops',ids:['route']},
] as const;

export const EVIDENCE_LAYERS: readonly EvidenceLayer[] = LAYER_GROUPS.flatMap(group=>group.ids.map(id=>ALL_LAYERS.find(layer=>layer.id===id)!));

export function stateLabel(state: EvidenceState): string {
  return state[0].toUpperCase() + state.slice(1);
}

export function canToggleLayer(layer: EvidenceLayer): boolean {
  return layer.renderable;
}
