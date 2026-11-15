import { useEffect, useState } from "react";
import type { useRoutePlanner } from "../services/useRoutePlanner.ts";
import { COORDINATE_SYSTEM, type MarsCoordinate } from "../types/api.ts";
import { validateRouteRequest } from "../services/routes.ts";

export default function CoordinateEditor({ planner }: { planner: ReturnType<typeof useRoutePlanner> }) {
  const [start, setStart] = useState("");
  const [goal, setGoal] = useState("");
  const [stops, setStops] = useState("");
  const [error, setError] = useState<string | null>(null);
  const print = (p: MarsCoordinate) => `${p.longitude}, ${p.latitude}`;
  useEffect(() => {
    setStart(planner.start ? print(planner.start) : "");
    setGoal(planner.goal ? print(planner.goal) : "");
    setStops(planner.waypoints.map(print).join("\n"));
  }, [planner.start, planner.goal, planner.waypoints]);
  function point(text: string): MarsCoordinate {
    const parts = text.split(/[,，]/).map((v) => v.trim());
    if (parts.length !== 2 || parts.some((v) => !v)) throw new Error("Enter longitude, latitude for each stop.");
    return { longitude: Number(parts[0]), latitude: Number(parts[1]) };
  }
  return <details className="coordinate-editor"><summary>{planner.interfaceMode === "advanced" ? "Enter API coordinates and ordered waypoints" : "Enter API coordinates"}</summary>
    <p>East longitude, planetocentric latitude. These inputs do not depend on basemap registration.</p>
    <form onSubmit={(event) => {
      event.preventDefault();
      try {
        const request = { region_id: "jezero" as const, coordinate_system: COORDINATE_SYSTEM, start: point(start), goal: point(goal),
          mode: planner.mode, waypoints: planner.interfaceMode === "advanced" ? stops.split("\n").filter((v) => v.trim()).map(point) : [] };
        validateRouteRequest(request); planner.loadExample(request); setError(null);
      } catch (error) { setError(error instanceof Error ? error.message : "Invalid route stops."); }
    }}>
      <label>Start: longitude, latitude<input value={start} onChange={(e) => setStart(e.target.value)} required /></label>
      <label>Goal: longitude, latitude<input value={goal} onChange={(e) => setGoal(e.target.value)} required /></label>
      {planner.interfaceMode === "advanced" && <label>Waypoints in visit order (one longitude, latitude per line; maximum 16)<textarea rows={5} value={stops} onChange={(e) => setStops(e.target.value)} /></label>}
      <button type="submit">Apply coordinates and stop order</button>
      {error && <p role="alert">{error}</p>}
    </form>
  </details>;
}
