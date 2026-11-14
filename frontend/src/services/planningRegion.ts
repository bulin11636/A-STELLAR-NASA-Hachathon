import { COORDINATE_SYSTEM, type PlanRouteRequest, type PlanningRegion } from "../types/api.ts";
import { apiRequest } from "./apiClient.ts";
import { validateRouteRequest } from "./routes.ts";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validBounds(value: unknown): boolean {
  if (!object(value)) return false;
  const { west,east,south,north } = value;
  return [west,east,south,north].every((v) => typeof v === "number" && Number.isFinite(v)) &&
    Number(west) >= 0 && Number(west) < Number(east) && Number(east) <= 360 &&
    Number(south) >= -90 && Number(south) < Number(north) && Number(north) <= 90;
}

export function decodePlanningRegion(body: unknown): PlanningRegion {
  if (!object(body) || !Array.isArray(body.regions)) throw new Error("Invalid region response.");
  const region = body.regions.find((item) => object(item) && item.id === "jezero");
  if (!object(region) || region.coordinate_system !== COORDINATE_SYSTEM ||
      typeof region.routing_available !== "boolean" || !["mock", "computed"].includes(String(region.routing_mode))) {
    throw new Error("Invalid Jezero planning region.");
  }
  // Older servers do not advertise a footprint. Never guess one in the client.
  if (region.planning === undefined) return { ...region, planning: null } as unknown as PlanningRegion;
  if (region.planning !== null) {
    const info = region.planning;
    if (!object(info) || typeof info.roi_id !== "string" || !info.roi_id || !object(info.bounds) ||
        !Array.isArray(info.resolution_m) || info.resolution_m.length !== 2 ||
        info.resolution_m.some((v) => typeof v !== "number" || !Number.isFinite(v) || v <= 0)) {
      throw new Error("Invalid planning footprint.");
    }
    const { west, east, south, north } = info.bounds;
    if (!validBounds(info.bounds)) {
      throw new Error("Invalid planning bounds.");
    }
    if (info.source_bounds != null && !validBounds(info.source_bounds)) throw new Error("Invalid source bounds.");
    if (info.dynamic_windowing !== undefined && typeof info.dynamic_windowing !== "boolean") throw new Error("Invalid dynamic planning configuration.");
    if (info.max_grid_cells != null && (typeof info.max_grid_cells !== "number" || !Number.isInteger(info.max_grid_cells) || info.max_grid_cells < 1 || info.max_grid_cells > 1_000_000)) throw new Error("Invalid search allocation limit.");
    if (info.example_request !== null) {
      if (!object(info.example_request)) throw new Error("Invalid example request.");
      const request = info.example_request as unknown as PlanRouteRequest;
      validateRouteRequest(request);
      for (const point of [request.start,...(request.waypoints ?? []),request.goal]) {
        if (!(point.longitude > Number(west) && point.longitude < Number(east) &&
              point.latitude > Number(south) && point.latitude < Number(north))) {
          throw new Error("Example endpoints lie outside the planning bounds.");
        }
      }
    }
    if (info.regional_example_request != null) {
      validateRouteRequest(info.regional_example_request as PlanRouteRequest);
      if (!object(info.source_bounds)) throw new Error("Regional example requires source bounds.");
      const request = info.regional_example_request as PlanRouteRequest;
      const bounds = info.source_bounds;
      for (const point of [request.start,...(request.waypoints ?? []),request.goal]) {
        if (!(point.longitude > Number(bounds.west) && point.longitude < Number(bounds.east) &&
              point.latitude > Number(bounds.south) && point.latitude < Number(bounds.north))) {
          throw new Error("Regional example endpoints lie outside source coverage.");
        }
      }
    }
  }
  return region as unknown as PlanningRegion;
}

export function getPlanningRegion(signal?: AbortSignal): Promise<PlanningRegion> {
  return apiRequest("/api/v1/regions", decodePlanningRegion, { signal });
}
