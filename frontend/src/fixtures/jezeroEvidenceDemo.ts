import type { MarsCoordinate } from "../types/api.ts";

export interface ScienceFixture extends MarsCoordinate {
  id: string;
  label: string;
  category: string;
  sourceUrl: string;
  rationale: string;
}

export interface RoverStopFixture extends MarsCoordinate {
  recordId: string;
  sol: number;
  observationUrl: string | null;
  sourceUrl: string;
}

export interface TraverseFixture {
  id: string;
  sol: number;
  points: readonly MarsCoordinate[];
}

export const JEZERO_EVIDENCE_DEMO = {
  evidenceState: "observed" as const,
  datasetVersion: "jezero-evidence-e4de0e69b0db0fd4:roi-310abb69784d:evidence-v2",
  coordinateSystem: "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  provenance: {
    snapshotManifest: "https://mars.nasa.gov/maps/location/api/configure/get?mission=M20",
    sampleSource: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_SAMPLE_v3.json",
    traverseSource: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json",
    waypointSource: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
    ingestionDate: "2026-11-14",
    limitations: [
      "Small selected subset only; it is not complete mission coverage.",
      "WMTS, wire-coordinate, and DEM registration remain unvalidated. Display is mock integration only.",
      "Historical rover activity is not astronaut-safety evidence.",
    ],
  },
  scienceSites: [
    { id: "nasa-m20-sample:1", label: "Roubion", category: "atmospheric", longitude: 77.45167282, latitude: 18.4276677,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_SAMPLE_v3.json",
      rationale: "Documented sample site Roubion at Roubion; historical science context only." },
    { id: "nasa-m20-sample:10 & 11", label: "Swift Run + Skyland", category: "rock_core", longitude: 77.40617493, latitude: 18.45893136,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_SAMPLE_v3.json",
      rationale: "Documented sample site at Skinner Ridge; no future sampling priority inferred." },
    { id: "nasa-m20-sample:12 & 13", label: "Hazeltop + Bearwallow", category: "rock_core", longitude: 77.40588851, latitude: 18.45863707,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_SAMPLE_v3.json",
      rationale: "Documented sample site at Wildcat Ridge; no future sampling priority inferred." },
    { id: "nasa-m20-sample:14 & 15", label: "Shuyak + Mageik", category: "rock_core", longitude: 77.40144029, latitude: 18.45072631,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_SAMPLE_v3.json",
      rationale: "Documented sample site at Amalik; no future sampling priority inferred." },
  ] as const satisfies readonly ScienceFixture[],
  roverStops: [
    { recordId: "3_0", sol: 13, longitude: 77.45088572, latitude: 18.44462715,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
      observationUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/mosaics/N_LRGB_0012XRAS_0030000_CYL_S_AUTOGENJ01.jpg" },
    { recordId: "3_110", sol: 14, longitude: 77.45094675, latitude: 18.44454338,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
      observationUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/mosaics/N_LFMM_0014_RAS_0030110_CYL_S_AUTOGENJ01.jpg" },
    { recordId: "3_386", sol: 15, longitude: 77.45103403, latitude: 18.44513505,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
      observationUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/mosaics/N_LRGB_0015_RAS_0030386_CYL_S_AUTOGENJ01.jpg" },
    { recordId: "3_578", sol: 16, longitude: 77.45149726, latitude: 18.4452799,
      sourceUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
      observationUrl: "https://mars.nasa.gov/mmgis-maps/M20/Layers/mosaics/N_LRGB_0016_RAS_0030578_CYL_S_AUTOGENJ01.jpg" },
  ] as const satisfies readonly RoverStopFixture[],
  traverse: [
    { id: "14:3_0:3_110:f4dc3f9ff8bd", sol: 14, points: [{ longitude: 77.45088573, latitude: 18.44462715 }, { longitude: 77.45090949, latitude: 18.44460606 }, { longitude: 77.45093425, latitude: 18.44458365 }, { longitude: 77.45094675, latitude: 18.44454338 }] },
    { id: "15:3_110:3_386:935b0ded2e84", sol: 15, points: [{ longitude: 77.45094675, latitude: 18.44454338 }, { longitude: 77.45093954, latitude: 18.44483616 }, { longitude: 77.45096443, latitude: 18.44500922 }, { longitude: 77.45103403, latitude: 18.44513505 }] },
    { id: "16:3_386:3_578:fe33347db598", sol: 16, points: [{ longitude: 77.45103403, latitude: 18.44513505 }, { longitude: 77.45122084, latitude: 18.44519392 }, { longitude: 77.45137897, latitude: 18.44524097 }, { longitude: 77.45149726, latitude: 18.4452799 }] },
  ] as const satisfies readonly TraverseFixture[],
} as const;
