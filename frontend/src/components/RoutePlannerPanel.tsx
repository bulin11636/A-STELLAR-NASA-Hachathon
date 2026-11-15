import { COORDINATE_NOTICE } from "../geo/marsCoordinates.ts";
import type { useRoutePlanner } from "../services/useRoutePlanner.ts";
import type { MarsCoordinate, PlanningRegion } from "../types/api.ts";
import CoordinateEditor from "./CoordinateEditor.tsx";
import RouteChat from "./RouteChat.tsx";
import RoutePreview from "./RoutePreview.tsx";
import A0Status from "./A0Status.tsx";
import RouteComparison from "./RouteComparison.tsx";
import { buildAdvancedContext } from "../services/advancedContext.ts";

function label(point: MarsCoordinate | null) {
  return point ? `${point.longitude.toFixed(6)}° E · ${point.latitude.toFixed(6)}° (API coordinates)` : "Not selected";
}

export default function RoutePlannerPanel({ planner, mapReady, onViewJezero, planningRegion, planningError }: {
  planner: ReturnType<typeof useRoutePlanner>;
  mapReady: boolean;
  onViewJezero: () => void;
  planningRegion?: PlanningRegion | null;
  planningError?: string | null;
}) {
  return (
    <section className="route-planner" aria-labelledby="route-planner-title">
      <h2 id="route-planner-title">Plan a research route</h2>
      <div className="pick-modes" role="tablist" aria-label="Planning mode">
        {(["quick", "advanced"] as const).map((value) => <button type="button" role="tab" key={value} aria-selected={planner.interfaceMode === value} onClick={() => planner.setInterfaceMode(value)}>{value === "quick" ? "Quick" : "Advanced"}</button>)}
      </div>
      <A0Status revision={planner.result?.route_id} />
      <p className="notice coordinate-caveat"><strong>{COORDINATE_NOTICE}</strong>. Computed geometry is hidden until NASA map registration is verified. Map picks use unverified native latitude.</p>
      <p>Region: Jezero · Terrain-only research policy; optional environmental constraints may be unassessed.</p>
      {planningError && <p role="alert">Planning information unavailable: {planningError}. Check the backend and reload this page.</p>}
      {planningRegion?.planning && <section aria-label="Backend planning footprint">
        <p>{planningRegion.planning.dynamic_windowing ? "Initial DEM example window (regional routes can use the full supported source):" : "Only this DEM window supports computed routing:"}</p>
        <p>Longitude {planningRegion.planning.bounds.west.toFixed(6)}–{planningRegion.planning.bounds.east.toFixed(6)}° E<br />
          Planetocentric latitude {planningRegion.planning.bounds.south.toFixed(6)}–{planningRegion.planning.bounds.north.toFixed(6)}°</p>
        <p>Grid: {planningRegion.planning.resolution_m.join(" × ")} m. Map coverage is larger than the planning window.</p>
        {planningRegion.planning.source_bounds && <p>Supported DEM source: longitude {planningRegion.planning.source_bounds.west.toFixed(4)}–{planningRegion.planning.source_bounds.east.toFixed(4)}° E;
          latitude {planningRegion.planning.source_bounds.south.toFixed(4)}–{planningRegion.planning.source_bounds.north.toFixed(4)}°. Each request is limited to {planningRegion.planning.max_grid_cells?.toLocaleString()} search cells; regional routes can use conservative aggregation with native-resolution segment checks.</p>}
        {planningRegion.planning.example_request && <>
          <button type="button" onClick={() => planner.loadExample(planningRegion.planning!.example_request!)}>Load in-coverage example endpoints</button>
          <p>The example uses coordinates from the loaded DEM. You can plan it without clicking the unverified basemap.</p>
        </>}
        {planningRegion.planning.regional_example_request && <>
          <button type="button" onClick={() => planner.loadExample(planningRegion.planning!.regional_example_request!)}>Load crater-scale example endpoints</button>
          <p>DEM-derived regional endpoints. Traversability, connection and search limits are checked when you plan.</p>
        </>}
      </section>}
      {planningRegion?.routing_mode === "computed" && planningRegion.routing_available && !planningRegion.planning && <p role="status">Planning bounds are unavailable. Restart the updated backend and reload this page.</p>}
      {planningRegion?.routing_mode === "computed" && !planningRegion.routing_available && <p role="alert">Computed routing is unavailable. Check the backend planning profile and dataset.</p>}
      <button type="button" disabled={!mapReady} onClick={onViewJezero}>View Jezero area</button>
      <fieldset disabled={!mapReady}>
        <legend>Map click action</legend>
        <div className="pick-modes">
          {(["inspect", "start", "goal", "waypoint"] as const).map((mode) => (
            <button type="button" key={mode} aria-pressed={planner.pickMode === mode} onClick={() => planner.setPickMode(mode)}>
              {mode === "inspect" ? "Inspect" : `Pick ${mode === "start" ? "Start" : mode === "goal" ? "Goal" : "Waypoint"}`}
            </button>
          ))}
        </div>
      </fieldset>
      <p className="pick-instruction" role="status">{planner.pickMode === "inspect" ? "Inspecting coordinates. Choose Pick Start, Pick Goal, or Pick Waypoint." : `Click the map to select ${planner.pickMode === "start" ? "Start (S)" : planner.pickMode === "goal" ? "Goal (G)" : "a required waypoint"}.`}</p>
      <dl className="selected-coordinates">
        <dt>Start (S)</dt><dd data-testid="start-coordinate">{label(planner.start)}</dd>
        <dt>Goal (G)</dt><dd data-testid="goal-coordinate">{label(planner.goal)}</dd>
      </dl>
      <CoordinateEditor planner={planner} />
      <section aria-label="Required waypoints"><p>Required waypoints: {planner.waypoints.length}/16 (visit order preserved).</p>
        <ol>{planner.waypoints.map((point, index) => <li key={`${point.longitude}:${point.latitude}:${index}`}>W{index + 1}: {label(point)} <button type="button" disabled={index === 0} onClick={() => planner.moveWaypoint(index, -1)}>Move up</button> <button type="button" disabled={index === planner.waypoints.length - 1} onClick={() => planner.moveWaypoint(index, 1)}>Move down</button> <button type="button" onClick={() => planner.removeWaypoint(index)}>Remove</button></li>)}</ol>
      </section>
      <label className="mode-label">Requested terrain objective
        <select value={planner.mode} onChange={(event) => planner.changeMode(event.target.value as "shortest" | "safest")}>
          <option value="safest">Safest</option><option value="shortest">Shortest</option>
        </select>
      </label>
      {planner.interfaceMode === "advanced" && <section aria-label="Advanced planning options">
        <fieldset><legend>Analysis focus</legend>{(["terrain", "science", "operations"] as const).map((focus) => <label key={focus}><input type="checkbox" checked={planner.analysisFocus.includes(focus)} onChange={() => planner.setAnalysisFocus(planner.analysisFocus.includes(focus) ? planner.analysisFocus.filter((item) => item !== focus) : [...planner.analysisFocus, focus])} /> {focus}</label>)}</fieldset>
        <label><input type="checkbox" checked={planner.allowSupportedRevision} onChange={(event) => planner.setAllowSupportedRevision(event.target.checked)} /> Allow A0 to propose a supported route revision</label>
        <label className="mode-label">Additional requirements<textarea maxLength={1600} rows={3} value={planner.additionalRequirements} onChange={(event) => planner.setAdditionalRequirements(event.target.value)} placeholder="Describe a bounded requirement for A0 to explain or evaluate." /></label>
      </section>}
      <div className="route-actions">
        <button type="button" disabled={!planner.start || !planner.goal || planner.status === "loading"} onClick={() => void planner.submit(planningRegion?.routing_mode === "computed")}>
          {planner.status === "loading" ? "Planning…" : "Plan Route"}
        </button>
        <button type="button" onClick={planner.clear}>Clear selections</button>
      </div>
      {planner.status === "loading" && <p role="status">Waiting for the backend… Changing selections cancels this request.</p>}
      {planner.error && <p className="notice route-error" role="alert"><strong>{planner.error.code}</strong>: {planner.error.message}{planner.error.status !== null && ` (HTTP ${planner.error.status})`}</p>}
      {planner.attemptStatus && <p role="status">Request {planner.attemptStatus.state}. Attempt {planner.attemptStatus.attempt}. {planner.attemptStatus.retry_allowed ? `Manual retry available after ${planner.attemptStatus.retry_after_seconds} seconds.` : "Manual retry is not available."}</p>}
      {planner.result && (
        <section className="route-result" aria-label="Route result" aria-live="polite">
          <strong className="mock-badge">{planner.result.source === "mock" ? "MOCK / NOT SAFETY-VALIDATED" : "COMPUTED / RESEARCH TERRAIN ONLY"}</strong>
          {planner.result.source === "computed" && <p className="notice">Computed geometry is withheld from the map: NASA map/wire/DEM registration is unverified.</p>}
          <p>Route <code>{planner.result.route_id}</code> · source: {planner.result.source} · mode: {planner.result.mode}</p>
          <dl className="route-metrics">
            <dt>Distance (m)</dt><dd>{planner.result.metrics.distance_m?.toFixed(1) ?? "—"}</dd>
            <dt>Estimated time (min)</dt><dd>{planner.result.metrics.estimated_time_min ?? "—"}</dd>
            <dt>Risk score</dt><dd>{planner.result.metrics.risk_score ?? "—"}</dd>
          </dl>
          {planner.metadataError && <p role="alert">Metadata unavailable: {planner.metadataError}</p>}
          {planner.metadata && <dl>
            <dt>Dataset / version</dt><dd>{planner.metadata.sources[0].dataset_id} / {planner.metadata.scope.dataset_version}</dd>
            <dt>Grid resolution (m)</dt><dd>{planner.metadata.grid.planning_resolution_m.join(" × ")}</dd>
            <dt>Research policy</dt><dd>{planner.metadata.policy.policy_id}; slope ≤ {planner.metadata.policy.slope_threshold_deg}°</dd>
            <dt>Map registration</dt><dd>{planner.metadata.validation.map_alignment}</dd>
            <dt>Specialists</dt><dd>{planner.metadata.workers.map((w) => `${w.public_name}: ${w.status}`).join("; ")}</dd>
          </dl>}
          {planner.metadata?.rationale && <section aria-label="Planning rationale"><h3>Planning rationale</h3>
            <p>{planner.metadata.rationale.summary}</p>
            <ul>{planner.metadata.rationale.facts.map((fact, i) => <li key={i}>{fact}</li>)}</ul>
            {planner.metadata.rationale.model_commentary && <p><strong>A0 interpretation:</strong> {planner.metadata.rationale.model_commentary}</p>}
            {planner.metadata.rationale.evidence_ids.length > 0 && <p>Evidence: {planner.metadata.rationale.evidence_ids.join(", ")}</p>}
          </section>}
          {planner.metadata && <RouteComparison current={{ result: planner.result, metadata: planner.metadata }} />}
          {planner.metadata && <RoutePreview result={planner.result} metadata={planner.metadata} />}
          {planner.metadata?.usage && <p>A0: {planner.metadata.usage.model} / {planner.metadata.usage.reasoning_effort} ·
            {planner.metadata.usage.input_tokens} input / {planner.metadata.usage.output_tokens} output tokens (including reasoning) · estimated ${planner.metadata.usage.estimated_cost_usd.toFixed(4)}</p>}
          {planner.result.source === "computed" && <RouteChat routeId={planner.result.route_id} onRevision={planner.acceptRevision} advancedContext={planner.interfaceMode === "advanced" && planner.analysisFocus.length ? buildAdvancedContext(planner.mode, planner.waypoints, planner.analysisFocus, planner.allowSupportedRevision) : undefined} />}
          <ul>{planner.result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </section>
      )}
    </section>
  );
}
