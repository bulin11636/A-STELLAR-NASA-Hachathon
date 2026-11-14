import { JEZERO_EVIDENCE_DEMO, type RoverStopFixture, type ScienceFixture } from "../fixtures/jezeroEvidenceDemo.ts";
import type { MarsCoordinate } from "../types/api.ts";

const MARS_SPHERE_RADIUS_M = 3_396_190;

export interface NearbyEvidence<T> {
  item: T;
  distance_m: number;
}

export interface LocationEvidence {
  point: MarsCoordinate;
  nearestScience: NearbyEvidence<ScienceFixture> | null;
  nearestRoverStop: NearbyEvidence<RoverStopFixture> | null;
  warnings: readonly string[];
}

function radians(value: number) {
  return value * Math.PI / 180;
}

export function marsSphereDistanceM(first: MarsCoordinate, second: MarsCoordinate): number {
  const latitudeDelta = radians(second.latitude - first.latitude);
  const longitudeDegrees = ((second.longitude - first.longitude + 540) % 360) - 180;
  const longitudeDelta = radians(longitudeDegrees);
  const firstLatitude = radians(first.latitude);
  const secondLatitude = radians(second.latitude);
  const a = Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(firstLatitude) * Math.cos(secondLatitude) * Math.sin(longitudeDelta / 2) ** 2;
  return MARS_SPHERE_RADIUS_M * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function nearest<T extends MarsCoordinate>(point: MarsCoordinate, values: readonly T[]): NearbyEvidence<T> | null {
  let result: NearbyEvidence<T> | null = null;
  for (const item of values) {
    const candidate = { item, distance_m: marsSphereDistanceM(point, item) };
    if (!result || candidate.distance_m < result.distance_m) result = candidate;
  }
  return result;
}

export function evidenceAtPoint(point: MarsCoordinate): LocationEvidence {
  return {
    point,
    nearestScience: nearest(point, JEZERO_EVIDENCE_DEMO.scienceSites),
    nearestRoverStop: nearest(point, JEZERO_EVIDENCE_DEMO.roverStops),
    warnings: [
      "Nearest results are from a small selected fixture, not full mission coverage.",
      "Distances use a Mars-sphere calculation on wire coordinates. WMTS, wire-coordinate, and DEM registration remain unvalidated.",
      "Terrain, thermal, and astronaut-safety evidence are unknown at this point.",
    ],
  };
}
