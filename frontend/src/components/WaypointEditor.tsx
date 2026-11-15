import { useState } from "react";
import type { useRoutePlanner } from "../services/useRoutePlanner.ts";

export default function WaypointEditor({ planner }: { planner: ReturnType<typeof useRoutePlanner> }) {
  const [longitude, setLongitude] = useState("");
  const [latitude, setLatitude] = useState("");
  return <section className="waypoint-editor" aria-label="Required waypoints">
    <h3>Required waypoints ({planner.waypoints.length}/16)</h3>
    <p>Visit order is preserved. Add a coordinate below or choose Pick Waypoint on the map.</p>
    <form onSubmit={event => {
      event.preventDefault();
      if (!longitude.trim() || !latitude.trim()) return;
      planner.addWaypoint({ longitude: Number(longitude), latitude: Number(latitude) });
    }}>
      <label>Waypoint longitude<input type="number" step="any" min="0" max="359.999999999" required value={longitude} onChange={event => setLongitude(event.target.value)} /></label>
      <label>Waypoint latitude<input type="number" step="any" min="-90" max="90" required value={latitude} onChange={event => setLatitude(event.target.value)} /></label>
      <button type="submit" disabled={planner.waypoints.length >= 16}>Add waypoint</button>
    </form>
    <ol>{planner.waypoints.map((point, index) => <li key={index}>
      W{index + 1}: {point.longitude.toFixed(7)}° E, {point.latitude.toFixed(7)}°
      <button type="button" aria-label={`Move W${index + 1} up`} disabled={index === 0} onClick={() => planner.moveWaypoint(index, -1)}>Move up</button>
      <button type="button" aria-label={`Move W${index + 1} down`} disabled={index === planner.waypoints.length - 1} onClick={() => planner.moveWaypoint(index, 1)}>Move down</button>
      <button type="button" aria-label={`Remove W${index + 1}`} onClick={() => planner.removeWaypoint(index)}>Remove</button>
    </li>)}</ol>
  </section>;
}
