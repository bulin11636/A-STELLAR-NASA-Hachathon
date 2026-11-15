import type { MarsCoordinate, RouteMode } from "../types/api.ts";

export type AnalysisFocus = "terrain" | "science" | "operations";
export interface AdvancedContext {
  schema_version: "1";
  interface_mode: "advanced";
  route_objective: RouteMode;
  required_waypoints: MarsCoordinate[];
  analysis_focus: readonly AnalysisFocus[];
  allow_supported_revision: boolean;
}

export function buildAdvancedContext(mode: RouteMode, waypoints: MarsCoordinate[], focus: readonly AnalysisFocus[], allowRevision: boolean): AdvancedContext {
  const unique = [...new Set(focus)];
  if (!unique.length || unique.length !== focus.length || unique.some(item => !["terrain", "science", "operations"].includes(item))) {
    throw new Error("Choose one or more unique analysis focus values.");
  }
  return { schema_version: "1", interface_mode: "advanced", route_objective: mode,
    required_waypoints: structuredClone(waypoints), analysis_focus: unique, allow_supported_revision: allowRevision };
}
