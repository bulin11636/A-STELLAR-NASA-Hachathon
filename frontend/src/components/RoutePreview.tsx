import type { PlanRouteResponse } from "../types/api.ts";
import type { RouteMetadata } from "../services/metadata.ts";
import { useEffect, useMemo, useRef, useState } from "react";
import { fitRoute, zoomViewport, type Viewport } from "../geo/routeViewport.ts";

export default function RoutePreview({ result, metadata }: { result: PlanRouteResponse; metadata: RouteMetadata }) {
  const bounds = metadata.scope.bounds;
  const width = metadata.grid.width * metadata.grid.planning_resolution_m[0];
  const height = metadata.grid.height * metadata.grid.planning_resolution_m[1];
  // The supported backend uses a native spherical equirectangular grid. This
  // standalone preview uses its linear axes; it is never a NASA overlay.
  const xy = (p: { longitude: number; latitude: number }) => [
    width * (p.longitude - bounds.west) / (bounds.east - bounds.west),
    height * (bounds.north - p.latitude) / (bounds.north - bounds.south),
  ];
  const projected = result.route.map(xy);
  const points = projected.map((p) => p.join(",")).join(" ");
  const stops = [result.route[0], ...metadata.request.waypoints, result.route[result.route.length - 1]];
  const nativeSpacing = Math.min(...metadata.grid.source_resolution);
  const initialView = useMemo(() => fitRoute(projected, nativeSpacing * 8), [result.route_id]);
  const [view, setView] = useState<Viewport>(initialView);
  const [focused, setFocused] = useState<number | null>(null);
  const figure = useRef<HTMLElement>(null);
  const [expanded, setExpanded] = useState(false);
  const drag = useRef<{ x: number; y: number; view: Viewport; width: number; height: number } | null>(null);
  useEffect(() => { setView(initialView); setFocused(null); }, [initialView]);
  useEffect(() => {
    if (typeof document === "undefined") return;
    const changed = () => setExpanded(document.fullscreenElement === figure.current);
    document.addEventListener("fullscreenchange",changed);
    return () => document.removeEventListener("fullscreenchange",changed);
  }, []);
  if (!(width > 0 && height > 0 && bounds.east > bounds.west && bounds.north > bounds.south)) return null;
  const size = view.width / 55;
  const stopLabel = (index: number) => index === 0 ? "S" : index === stops.length - 1 ? "G" : String(index);
  const visibleLabels: number[][] = [];
  return <figure ref={figure} className="route-preview"><figcaption>DEM route preview · {metadata.grid.planning_resolution_m.join(" × ")} m cells</figcaption>
    <div className="preview-controls" aria-label="DEM preview controls">
      <button type="button" onClick={() => { setView(initialView); setFocused(null); }}>Fit route</button>
      <button type="button" onClick={() => {
        if (document.fullscreenElement === figure.current) void document.exitFullscreen().catch(() => {});
        else void figure.current?.requestFullscreen?.().catch(() => {});
      }}>{expanded ? "Close expanded preview" : "Expand preview"}</button>
      <button type="button" onClick={() => setView(fitRoute([[0,0],[width,height]], nativeSpacing * 8))}>Full planning area</button>
      <button type="button" aria-label="Zoom in DEM preview" onClick={() => setView((v) => zoomViewport(v, .5, nativeSpacing / 4, Math.max(width,height) * 4))}>+</button>
      <button type="button" aria-label="Zoom out DEM preview" onClick={() => setView((v) => zoomViewport(v, 2, nativeSpacing / 4, Math.max(width,height) * 4))}>−</button>
    </div>
    <svg viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} role="img" aria-label="Computed route on the native DEM planning axes"
      onPointerDown={(event) => { const rect = event.currentTarget.getBoundingClientRect(); drag.current = { x: event.clientX, y: event.clientY, view, width: rect.width, height: rect.height }; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={(event) => { const start = drag.current; if (start) { const pixels = Math.min(start.width,start.height); setView({ ...start.view, x: start.view.x - (event.clientX-start.x)*start.view.width/pixels, y: start.view.y - (event.clientY-start.y)*start.view.height/pixels }); } }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <rect width={width} height={height} fill="#16232d" stroke="#627887" strokeWidth={size / 5} />
      <polyline points={points} fill="none" stroke="#f5c27b" strokeWidth={size / 3} />
      {stops.map((p, i) => { const [x, y] = xy(p);
        const label = focused === i || !visibleLabels.some(([px,py]) => Math.hypot(px-x,py-y) < size * 4);
        if (label) visibleLabels.push([x,y]);
        return <g key={i}>
        <circle cx={x} cy={y} r={focused === i ? size : size / 2} fill={i === 0 ? "#77edc2" : "#ffb59e"} />
        {label && <text x={x + size} y={y} fontSize={size * 1.5} fill="white">{stopLabel(i)}</text>}
      </g>; })}
    </svg>
    <p>View width: {view.width >= 1000 ? `${(view.width/1000).toFixed(2)} km` : `${view.width.toFixed(1)} m`}. Drag to pan; use + / − to zoom. Select a stop to separate nearby locations.</p>
    <div className="preview-stops" aria-label="Focus route stops">{stops.map((p,i) => <button type="button" key={i} aria-pressed={focused === i}
      title={`${p.longitude.toFixed(7)}, ${p.latitude.toFixed(7)}`}
      onClick={() => { const [x,y] = xy(p); const span = nativeSpacing * 8; setView({ x: x-span/2, y: y-span/2, width: span, height: span }); setFocused(i); }}>
      Focus {stopLabel(i)}</button>)}</div>
    <p>Validated route geometry on DEM axes. Terrain costs are not drawn. NASA basemap registration remains unverified.</p>
  </figure>;
}
