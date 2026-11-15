import type { WalkingMission } from "./routeMetadata.ts";
export type { WalkingMission } from "./routeMetadata.ts";

export const COORDINATE_SYSTEM = "MARS_2000_PLANETOCENTRIC_EAST_360_V1" as const;
export type CoordinateSystem = typeof COORDINATE_SYSTEM;
export type RouteMode = "shortest" | "safest";
export type RouteSource = "mock" | "computed";
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface MarsCoordinate {
  longitude: number;
  latitude: number;
}

export interface PlanRouteRequest {
  region_id: "jezero";
  coordinate_system: CoordinateSystem;
  start: MarsCoordinate;
  goal: MarsCoordinate;
  mode: RouteMode;
  waypoints?: MarsCoordinate[];
  mission?: WalkingMission | null;
  mission_profile?: "safest" | "fastest" | "science_priority" | "balanced" | null;
  resolution_profile?: "coarse" | "standard" | "fine" | null;
}

export interface PlanRouteResponse {
  status: "success";
  route_id: string;
  region_id: string;
  coordinate_system: CoordinateSystem;
  mode: RouteMode;
  source: RouteSource;
  route: MarsCoordinate[];
  metrics: {
    distance_m: number | null;
    estimated_time_min: number | null;
    risk_score: number | null;
  };
  warnings: string[];
}

export interface HealthResponse {
  status: "ok";
  service: "a-stellar-backend";
  api_version: "v1";
}

export interface ErrorEnvelope {
  error: { code: string; message: string; details: JsonValue };
}

export interface PlanningInfo {
  roi_id: string;
  bounds: { west: number; east: number; south: number; north: number };
  resolution_m: [number, number];
  example_request: PlanRouteRequest | null;
  regional_example_request?: PlanRouteRequest | null;
  source_bounds?: { west: number; east: number; south: number; north: number } | null;
  dynamic_windowing?: boolean;
  max_grid_cells?: number | null;
}

export interface PlanningRegion {
  id: "jezero";
  coordinate_system: CoordinateSystem;
  routing_available: boolean;
  routing_mode: RouteSource;
  planning: PlanningInfo | null;
}
