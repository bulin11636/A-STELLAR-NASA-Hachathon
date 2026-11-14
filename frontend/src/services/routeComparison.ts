import type { RouteMetadata } from "./metadata.ts";
import type { PlanRouteResponse } from "../types/api.ts";

export type ComparisonRoute = { metadata: RouteMetadata; result: Pick<PlanRouteResponse, "metrics"> };

export function compareRoutes(parent: ComparisonRoute, current: ComparisonRoute) {
  const a = parent.metadata, b = current.metadata;
  if (b.parent_route_id !== a.route_id) throw new Error("The comparison route is not the stored parent.");
  const sameSource = a.scope.dataset_version === b.scope.dataset_version && a.grid.planning_crs === b.grid.planning_crs;
  const objectiveComparable = sameSource && a.request.mode === b.request.mode &&
    a.policy.slope_threshold_deg === b.policy.slope_threshold_deg && a.policy.cost_formula === b.policy.cost_formula &&
    JSON.stringify(a.policy.parameters) === JSON.stringify(b.policy.parameters) &&
    a.grid.planning_resolution_m.every((v,i) => v === b.grid.planning_resolution_m[i]);
  const distanceDelta = sameSource ? current.result.metrics.distance_m! - parent.result.metrics.distance_m! : null;
  const objectiveDelta = objectiveComparable ? b.planner.objective_cost - a.planner.objective_cost : null;
  const pointKey = (p: { longitude: number; latitude: number }) => `${p.longitude},${p.latitude}`;
  const before = a.request.waypoints.map(pointKey), after = b.request.waypoints.map(pointKey);
  const excessVisits = (available: string[], visits: string[]) => {
    const counts = new Map<string,number>();
    available.forEach((p) => counts.set(p,(counts.get(p) ?? 0)+1));
    let excess = 0;
    visits.forEach((p) => { const remaining = counts.get(p) ?? 0; if (remaining) counts.set(p,remaining-1); else excess++; });
    return excess;
  };
  return { distanceDelta, objectiveDelta, modeBefore: a.request.mode, modeAfter: b.request.mode,
    stopsBefore: before.length, stopsAfter: after.length,
    added: excessVisits(before,after),
    removed: excessVisits(after,before),
    orderChanged: JSON.stringify(before) !== JSON.stringify(after),
    resolutionChanged: a.grid.planning_resolution_m.some((v,i) => v !== b.grid.planning_resolution_m[i]),
  };
}
