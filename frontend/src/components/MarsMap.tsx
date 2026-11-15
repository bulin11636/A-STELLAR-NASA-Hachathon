import { useEffect, useRef, useState } from "react";
import Map from "ol/Map.js";
import View from "ol/View.js";
import ScaleLine from "ol/control/ScaleLine.js";
import { defaults as defaultControls } from "ol/control/defaults.js";
import TileLayer from "ol/layer/Tile.js";
import TileState from "ol/TileState.js";
import { containsCoordinate, intersects } from "ol/extent.js";
import { CAPABILITIES_URL, CATALOG_URL, JEZERO_LAYER_ID, LAYER_ID, loadMarsWmts } from "../map/marsWmts";
import { mapViewToApiCoordinate } from "../geo/marsCoordinates.ts";
import { createRouteOverlay, updateRouteOverlay } from "../map/routeOverlay.ts";
import { createEvidenceOverlays, type SelectedEvidence } from "../map/evidenceOverlays.ts";
import { useRoutePlanner } from "../services/useRoutePlanner.ts";
import { getPlanningRegion } from "../services/planningRegion.ts";
import type { PlanningRegion } from "../types/api.ts";
import { evidenceAtPoint } from "../services/evidenceAtPoint.ts";
import RoutePlannerPanel from "./RoutePlannerPanel";
import LayerPanel, { type LayerDisplayState } from "./LayerPanel.tsx";
import EvidenceSelection from "./EvidenceSelection.tsx";
import EvidenceDrawer from "./EvidenceDrawer.tsx";
import MissionBriefing from "./MissionBriefing.tsx";
import RouteAssessment from "./RouteAssessment.tsx";
import SpecialistTrace from "./SpecialistTrace.tsx";

type Progress = { pending: number; loaded: number; missing: number; failed: number };
type SidebarTab = "plan" | "route" | "briefing" | "evidence";
const initialProgress: Progress = { pending: 0, loaded: 0, missing: 0, failed: 0 };

export default function MarsMap() {
  const target = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const overlayRef = useRef<ReturnType<typeof createRouteOverlay> | null>(null);
  const basemapRef = useRef<TileLayer | null>(null);
  const jezeroImageryRef = useRef<TileLayer | null>(null);
  const evidenceOverlayRef = useRef<ReturnType<typeof createEvidenceOverlays> | null>(null);
  const planner = useRoutePlanner();
  const [planningRegion, setPlanningRegion] = useState<PlanningRegion | null>(null);
  const [planningError, setPlanningError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getPlanningRegion(controller.signal).then((region) => {
      if (!controller.signal.aborted) setPlanningRegion(region);
    }).catch((error) => {
      if (!controller.signal.aborted) setPlanningError(error instanceof Error ? error.message : "Planning information unavailable.");
    });
    return () => controller.abort();
  }, []);
  const pickRef = useRef(planner);
  useEffect(() => { pickRef.current = planner; });
  const [attempt, setAttempt] = useState(0);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress>(initialProgress);
  const [coordinates, setCoordinates] = useState<string | null>(null);
  const [outsideCoverage, setOutsideCoverage] = useState(false);
  const [layerDisplay, setLayerDisplay] = useState<Record<string, LayerDisplayState>>({
    mars_basemap: { visible: true, opacity: 1 },
    jezero_imagery: { visible: true, opacity: 1 },
    science_pois: { visible: false, opacity: 1 },
    rover_history: { visible: false, opacity: 1 },
  });
  const layerDisplayRef = useRef(layerDisplay);
  useEffect(() => { layerDisplayRef.current = layerDisplay; }, [layerDisplay]);
  const [evidenceSelection, setEvidenceSelection] = useState<SelectedEvidence | null>(null);
  const [inspectedPoint, setInspectedPoint] = useState<import("../types/api.ts").MarsCoordinate | null>(null);
  const [missionObjective, setMissionObjective] = useState("Inspect Jezero science and historical rover evidence without treating the demonstration route as safety validated.");
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("plan");

  useEffect(() => {
    const controller = new AbortController();
    let map: Map | undefined;
    const objectUrls = new Set<string>();
    setReady(false);
    setError(null);
    setProgress(initialProgress);
    setCoordinates(null);
    setOutsideCoverage(false);
    const update = (values: Partial<Progress>) => {
      if (!controller.signal.aborted) {
        setProgress((previous) => ({
          pending: previous.pending + (values.pending ?? 0),
          loaded: previous.loaded + (values.loaded ?? 0),
          missing: previous.missing + (values.missing ?? 0),
          failed: previous.failed + (values.failed ?? 0),
        }));
      }
    };

    loadMarsWmts(controller.signal).then(({ source, projection, extent, resolutions }) => {
      if (controller.signal.aborted || !target.current) return;

      // Fetch allows a bounded timeout and distinguishes an explicitly missing
      // tile (404/204/empty response) from network/server errors. Missing tiles
      // are not proof of no coverage: this is stated in the UI.
      source.setTileLoadFunction((tile, url) => {
        update({ pending: 1 });
        void (async () => {
          try {
            const response = await fetch(url, {
              signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
            });
            if (response.status === 404 || response.status === 204) {
              tile.setState(TileState.EMPTY);
              update({ missing: 1 });
              return;
            }
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            if (!blob.size) {
              tile.setState(TileState.EMPTY);
              update({ missing: 1 });
              return;
            }
            if (controller.signal.aborted) return;
            const image = (tile as import("ol/ImageTile.js").default).getImage() as HTMLImageElement;
            const objectUrl = URL.createObjectURL(blob);
            objectUrls.add(objectUrl);
            try {
              image.src = objectUrl;
              await image.decode();
              update({ loaded: 1 });
            } finally {
              URL.revokeObjectURL(objectUrl);
              objectUrls.delete(objectUrl);
            }
          } catch {
            if (!controller.signal.aborted) {
              tile.setState(TileState.ERROR);
              update({ failed: 1 });
            }
          } finally {
            update({ pending: -1 });
          }
        })();
      });

      const overlay = createRouteOverlay();
      overlayRef.current = overlay;
      const evidence = createEvidenceOverlays();
      evidenceOverlayRef.current = evidence;
      const basemap = new TileLayer({ source, extent });
      basemapRef.current = basemap;
      map = new Map({
        target: target.current,
        layers: [basemap, evidence.traverseLayer, evidence.scienceLayer, overlay.layer],
        controls: defaultControls().extend([new ScaleLine({ units: "metric", bar: true, steps: 4, text: true, minWidth: 110 })]),
        view: new View({
          projection, center: [0, 0], resolutions, extent: projection.getExtent(),
          constrainOnlyCenter: true, showFullExtent: true,
        }),
      });
      mapRef.current = map;
      map.getView().fit([77.0, 17.95, 78.1, 18.95], { padding: [32, 32, 32, 32] });
      void loadMarsWmts(controller.signal, JEZERO_LAYER_ID).then(({ source: jezeroSource, extent: jezeroExtent }) => {
        if (controller.signal.aborted || !map) return;
        const display = layerDisplayRef.current.jezero_imagery;
        const jezeroImagery = new TileLayer({ source: jezeroSource, extent: jezeroExtent, visible: display?.visible ?? true, opacity: display?.opacity ?? 1 });
        jezeroImagery.setZIndex(1);
        map.addLayer(jezeroImagery);
        jezeroImageryRef.current = jezeroImagery;
      }).catch(() => {
        // The global NASA map remains usable if the optional Jezero mosaic is unavailable.
      });
      map.on("singleclick", (event) => {
        const evidence = map?.forEachFeatureAtPixel(event.pixel, (feature) => {
          const kind = feature.get("kind");
          const item = feature.get("evidence");
          return (kind === "science" || kind === "rover_stop") && item ? { kind, item } as SelectedEvidence : undefined;
        }, {
          hitTolerance: 6,
          layerFilter: (layer) => layer === evidenceOverlayRef.current?.scienceLayer,
        });
        setEvidenceSelection(evidence ?? null);
        setInspectedPoint(null);
        if (!containsCoordinate(extent, event.coordinate)) {
          setCoordinates("Outside the layer’s advertised coverage.");
          if (pickRef.current.pickMode !== "inspect") pickRef.current.selectionError("Select a point inside NASA's advertised map coverage.");
          return;
        }
        const [x, y] = event.coordinate;
        try {
          setInspectedPoint(mapViewToApiCoordinate([x, y], "wmts-display"));
        } catch {
          setInspectedPoint(null);
        }
        setCoordinates(`X ${x.toFixed(4)}° · Y ${y.toFixed(4)}°`);
        if (pickRef.current.pickMode !== "inspect") {
          try { pickRef.current.selectPoint(mapViewToApiCoordinate([x, y], "wmts-display")); }
          catch (reason) { pickRef.current.selectionError(reason instanceof Error ? reason.message : "Invalid map coordinate."); }
        }
      });
      map.on("moveend", () => {
        if (map) setOutsideCoverage(!intersects(extent, map.getView().calculateExtent(map.getSize())));
      });
      setReady(true);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "Could not load NASA metadata.");
      }
    });

    return () => {
      controller.abort();
      mapRef.current = null;
      overlayRef.current = null;
      basemapRef.current = null;
      jezeroImageryRef.current = null;
      evidenceOverlayRef.current = null;
      map?.setTarget(undefined);
      map?.dispose();
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [attempt]);

  useEffect(() => {
    const display = layerDisplay.mars_basemap;
    if (basemapRef.current && display) {
      basemapRef.current.setVisible(display.visible);
      basemapRef.current.setOpacity(display.opacity);
    }
    const jezeroImagery = layerDisplay.jezero_imagery;
    if (jezeroImageryRef.current && jezeroImagery) {
      jezeroImageryRef.current.setVisible(jezeroImagery.visible);
      jezeroImageryRef.current.setOpacity(jezeroImagery.opacity);
    }
    const evidence = evidenceOverlayRef.current;
    if (evidence) {
      const sciencePois = layerDisplay.science_pois;
      const rover = layerDisplay.rover_history;
      if (sciencePois) {
        evidence.scienceLayer.setVisible(sciencePois.visible);
        evidence.scienceLayer.setOpacity(sciencePois.opacity);
      }
      if (rover) {
        evidence.traverseLayer.setVisible(rover.visible);
        evidence.traverseLayer.setOpacity(rover.opacity);
      }
    }
  }, [layerDisplay, ready]);

  useEffect(() => {
    if (overlayRef.current) updateRouteOverlay(overlayRef.current.source, planner.start, planner.goal, planner.result,
      planner.interfaceMode === "advanced" ? planner.waypoints : [], planner.metadata?.validation.map_alignment);
  }, [ready, planner.start, planner.goal, planner.result, planner.metadata?.validation.map_alignment, planner.interfaceMode, planner.waypoints]);

  const tileIssue = progress.failed > 0 || progress.missing > 0;
  const status = error ? error : !ready ? "Loading NASA WMTS metadata…"
    : outsideCoverage ? "No coverage in this view."
    : progress.pending > 0 ? `Loading NASA tiles… ${progress.pending} pending`
    : tileIssue && progress.loaded > 0 ? "NASA imagery partially loaded; some tiles are unavailable."
    : progress.loaded > 0 ? "NASA imagery loaded"
    : tileIssue ? "No imagery received. Check the tile status below."
    : "Waiting for NASA tiles…";

  return (
    <section className="explorer" aria-label="Mars map explorer">
      <div className="map-frame">
        <div className="map" ref={target} tabIndex={0} aria-label="Interactive Mars map. Drag to pan, use plus and minus to zoom, click to inspect coordinates." />
        <div className={`map-status ${error || tileIssue ? "warning" : ""}`} role={error ? "alert" : "status"}>
          {status}
        </div>
      </div>
      <aside className="map-info">
        <div className="info-heading"><h2>Explore the surface</h2><span className="badge">F1.5</span></div>
        <p>Drag to pan. Scroll, pinch, or use + / − to zoom. Focus the map to use arrow keys. Click to inspect a location.</p>
        <div className="coordinates" aria-live="polite">{coordinates ?? "Click the map to inspect coordinates."}</div>
        <div className="workspace-tabs" role="tablist" aria-label="Mission workspace">
          {(["plan", "route", "briefing", "evidence"] as const).map((tab) => <button type="button" key={tab} id={`${tab}-tab`} role="tab"
            aria-selected={sidebarTab === tab} aria-controls={`${tab}-panel`} onClick={() => setSidebarTab(tab)}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}
        </div>
        {sidebarTab === "plan" && <section id="plan-panel" role="tabpanel" aria-labelledby="plan-tab">
        <RoutePlannerPanel planner={planner} mapReady={ready} planningRegion={planningRegion} planningError={planningError} onViewJezero={() => {
          mapRef.current?.getView().fit([76.7912789, 17.5791654, 77.7314417, 18.6926322], { padding: [32, 32, 32, 32], duration: 300 });
        }} />
        </section>}
        {sidebarTab === "route" && <section id="route-panel" role="tabpanel" aria-labelledby="route-tab" className="route-workspace">
          <div className="info-heading"><h2>Route assessment</h2><span className="badge">P1</span></div>
          {!planner.result ? <p>Plan a route to view distance, timing, gate status, and specialist evidence.</p> : <>
            <dl className="route-metrics">
              <dt>Distance</dt><dd>{planner.result.metrics.distance_m?.toFixed(1) ?? "Not assessed"} m</dd>
              <dt>Estimated time</dt><dd>{planner.result.metrics.estimated_time_min?.toFixed(1) ?? "Not estimated"} min</dd>
              <dt>Map alignment</dt><dd>{planner.metadata?.validation.map_alignment ?? "Unassessed"}</dd>
              <dt>Grid resolution</dt><dd>{planner.metadata?.grid.planning_resolution_m.join(" × ") ?? "Not available"} m</dd>
            </dl>
            {planner.metadata ? <><RouteAssessment assessment={planner.metadata.assessment} /><SpecialistTrace traces={planner.metadata.specialist_trace} /></> : <p>Route metadata is not available yet.</p>}
          </>}
        </section>}
        {sidebarTab === "evidence" && <section id="evidence-panel" role="tabpanel" aria-labelledby="evidence-tab">
        <LayerPanel layers={layerDisplay} onLayerChange={(id, change) => {
          setLayerDisplay((current) => ({ ...current, [id]: { ...(current[id] ?? { visible: false, opacity: 1 }), ...change } }));
        }} />
        <EvidenceSelection selection={evidenceSelection} />
        <EvidenceDrawer evidence={inspectedPoint ? evidenceAtPoint(inspectedPoint) : null} />
        </section>}
        {sidebarTab === "briefing" && <section id="briefing-panel" role="tabpanel" aria-labelledby="briefing-tab">
        <MissionBriefing objective={missionObjective} onObjectiveChange={setMissionObjective}
          start={planner.start} goal={planner.goal} route={planner.result} assessment={planner.metadata?.assessment ?? null} layers={layerDisplay}
          evidence={inspectedPoint ? evidenceAtPoint(inspectedPoint) : null} />
        </section>}
        {sidebarTab === "evidence" && <>
        <dl>
          <dt>Coordinate system</dt><dd>Mars 2000 · NASA service label <code>urn:ogc:def:crs:EPSG::104905</code> (ESRI:104905 definition)</dd>
          <dt>Native units and axes</dt><dd>Degrees · X longitude, east positive (−180° to +180°); Y native latitude (−90° to +90°).</dd>
          <dt>Latitude convention</dt><dd>WMTS planetographic latitude is converted to/from the API's Mars 2000 planetocentric latitude. WMTS/DEM pixel registration remains unverified.</dd>
          <dt>Basemap</dt><dd>NASA MGS MOLA global color hillshade <code>{LAYER_ID}</code></dd>
          <dt>High-resolution overlay</dt><dd>NASA Jezero HiRISE / CTX / HRSC mosaic <code>{JEZERO_LAYER_ID}</code></dd>
          <dt>Registration</dt><dd>{planner.metadata?.validation.map_alignment === "verified"
            ? "Verified only for this route's independently controlled footprint."
            : "Pending independent NASA WMTS, wire-coordinate, and DEM feature controls. Computed geometry remains hidden."}</dd>
        </dl>
        <div className="tile-summary" aria-live="polite">
          <p>Tiles this session: {progress.loaded} received · {progress.missing} missing · {progress.failed} failed</p>
          {progress.missing > 0 && <p className="notice">NASA returned missing or empty tiles. Coverage gaps and temporary unavailability cannot be distinguished.</p>}
          {progress.failed > 0 && <p className="notice">Some NASA tiles failed or timed out. Check your connection and retry.</p>}
          {error && <p className="notice">Metadata could not be loaded or verified. Check your connection and the NASA service link.</p>}
        </div>
        <button type="button" onClick={() => setAttempt((value) => value + 1)}>Reload NASA map</button>
        <p className="sources"><a href={CAPABILITIES_URL} target="_blank" rel="noreferrer">WMTS metadata ↗</a><a href={CATALOG_URL} target="_blank" rel="noreferrer">NASA source catalog ↗</a></p>
        <p className="credit">NASA / JPL-Caltech · Mars Global Surveyor / MOLA. Colorized topography, not natural-color photography.</p>
        </>}
      </aside>
    </section>
  );
}
