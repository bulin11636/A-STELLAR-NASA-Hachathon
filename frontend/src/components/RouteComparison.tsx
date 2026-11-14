import { useEffect, useState } from "react";
import { getStoredRoute, type StoredRouteResponse } from "../services/metadata.ts";
import { compareRoutes, type ComparisonRoute } from "../services/routeComparison.ts";

export default function RouteComparison({ current }: { current: ComparisonRoute }) {
  const parentId = current.metadata.parent_route_id;
  const [parent, setParent] = useState<StoredRouteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setParent(null); setError(null);
    if (!parentId) return;
    const controller = new AbortController();
    getStoredRoute(parentId,controller.signal).then((record) => { if (!controller.signal.aborted) setParent(record); })
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Parent route unavailable."); });
    return () => controller.abort();
  }, [parentId]);
  if (!parentId) return null;
  const comparison = parent && parent.result.route_id === parentId ? compareRoutes(parent,current) : null;
  const delta = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}`;
  return <section aria-label="Route revision comparison"><h3>Changes from previous route</h3>
    <p>Parent: <code>{parentId}</code></p>
    {error && <p role="status">Comparison unavailable: {error}</p>}
    {!comparison && !error && <p role="status">Loading the stored parent route…</p>}
    {comparison && <ul>
      <li>Projected distance change: {comparison.distanceDelta === null ? "not comparable across different source frames" : `${delta(comparison.distanceDelta)} m`}.</li>
      <li>Objective: {comparison.modeBefore} → {comparison.modeAfter}. {comparison.objectiveDelta === null ? "Objective costs are not compared across different modes, resolutions or cost policies." : `Cost change: ${delta(comparison.objectiveDelta)} ${current.metadata.planner.objective_units}.`}</li>
      <li>Required waypoints: {comparison.stopsBefore} → {comparison.stopsAfter}; {comparison.added} added, {comparison.removed} removed. {comparison.orderChanged ? "The ordered waypoint list changed." : "The waypoint order is unchanged."}</li>
      {comparison.resolutionChanged && <li>The search resolution changed; inspect the grid metadata and aggregation limitations.</li>}
    </ul>}
    <p>Comparison uses persisted results. It does not attribute a distance change to a single preference or establish a safety improvement.</p>
  </section>;
}
