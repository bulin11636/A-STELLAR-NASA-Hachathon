import type { MarsCoordinate } from "../types/api.ts";

// Route/API values are Mars 2000 planetocentric coordinates on a sphere. The
// Mars Trek WMTS CRS (ESRI:104905) is Mars 2000 planetographic coordinates on
// the IAU/IAG ellipsoid. Longitude is unchanged; latitude is not.
export const MARS_2000_SEMI_MAJOR_M = 3_396_190;
export const MARS_2000_INVERSE_FLATTENING = 169.894447223612;
export const COORDINATE_ADAPTER_VALIDATED = true;
// Datum conversion alone cannot prove pixel registration of this WMTS layer to
// the local DEM. That stays an independent acceptance gate for computed routes.
export const MAP_REGISTRATION_VALIDATED = false;
export const COORDINATE_CONVENTION_VALIDATED = COORDINATE_ADAPTER_VALIDATED;
export const COORDINATE_NOTICE = "WMTS/DEM registration has not been independently verified";
export type MapViewCoordinate = readonly [number, number];
export type CoordinateUse = "mock-integration-only" | "wmts-display";

export function validateApiCoordinate(value: unknown): asserts value is MarsCoordinate {
  if (typeof value !== "object" || value === null) throw new Error("Coordinates must be named longitude/latitude fields.");
  const point = value as MarsCoordinate;
  if (!Number.isFinite(point.longitude) || point.longitude < 0 || point.longitude >= 360 ||
      !Number.isFinite(point.latitude) || point.latitude < -90 || point.latitude > 90) {
    throw new Error("Coordinates require finite numeric longitude in [0, 360) and latitude in [-90, 90].");
  }
}

function requireSupportedUse(use: CoordinateUse) {
  if (use !== "mock-integration-only" && use !== "wmts-display") throw new Error("Unsupported Mars coordinate display mode.");
}

function planetographicLatitude(planetocentricDegrees: number): number {
  if (Math.abs(planetocentricDegrees) === 90) return planetocentricDegrees;
  const b = MARS_2000_SEMI_MAJOR_M * (1 - 1 / MARS_2000_INVERSE_FLATTENING);
  return Math.atan((MARS_2000_SEMI_MAJOR_M ** 2 / b ** 2) * Math.tan(planetocentricDegrees * Math.PI / 180)) * 180 / Math.PI;
}

function planetocentricLatitude(planetographicDegrees: number): number {
  if (Math.abs(planetographicDegrees) === 90) return planetographicDegrees;
  const b = MARS_2000_SEMI_MAJOR_M * (1 - 1 / MARS_2000_INVERSE_FLATTENING);
  return Math.atan((b ** 2 / MARS_2000_SEMI_MAJOR_M ** 2) * Math.tan(planetographicDegrees * Math.PI / 180)) * 180 / Math.PI;
}

// The legacy mock mode retains fixture arithmetic. API/DEM/PDS coordinates
// use wmts-display to make the documented datum conversion explicit.
export function mapViewToApiCoordinate(view: readonly number[], use: CoordinateUse): MarsCoordinate {
  requireSupportedUse(use);
  if (view.length !== 2 || !Number.isFinite(view[0]) || view[0] < -180 || view[0] > 180 ||
      !Number.isFinite(view[1]) || view[1] < -90 || view[1] > 90) {
    throw new Error("The selected point is outside the native Mars angular coordinate range.");
  }
  const point = { longitude: view[0] < 0 ? view[0] + 360 : view[0], latitude: use === "wmts-display" ? planetocentricLatitude(view[1]) : view[1] };
  validateApiCoordinate(point);
  return point;
}

export function apiCoordinateToMapView(point: MarsCoordinate, use: CoordinateUse): [number, number] {
  requireSupportedUse(use);
  validateApiCoordinate(point);
  return [point.longitude >= 180 ? point.longitude - 360 : point.longitude, use === "wmts-display" ? planetographicLatitude(point.latitude) : point.latitude];
}

// Split at the display seam instead of drawing a false line across Mars.
export function routeToMapSegments(route: MarsCoordinate[], use: CoordinateUse): number[][][] {
  const points = route.map((point) => apiCoordinateToMapView(point, use));
  if (points.length < 2) throw new Error("A route requires at least two vertices.");
  const segments: number[][][] = [[points[0]]];
  for (let index = 1; index < points.length; index++) {
    const previous = points[index - 1];
    const next = points[index];
    const delta = next[0] - previous[0];
    if (Math.abs(delta) > 180) {
      const adjustedX = next[0] + (delta > 0 ? -360 : 360);
      const boundary = delta > 0 ? -180 : 180;
      const fraction = (boundary - previous[0]) / (adjustedX - previous[0]);
      const latitude = previous[1] + fraction * (next[1] - previous[1]);
      segments[segments.length - 1].push([boundary, latitude]);
      segments.push([[-boundary, latitude], next]);
    } else segments[segments.length - 1].push(next);
  }
  return segments;
}
