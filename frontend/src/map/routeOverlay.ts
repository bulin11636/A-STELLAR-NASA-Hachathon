import Feature from "ol/Feature.js";
import Point from "ol/geom/Point.js";
import MultiLineString from "ol/geom/MultiLineString.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { Circle, Fill, Stroke, Style, Text } from "ol/style.js";
import { apiCoordinateToMapView, routeToMapSegments } from "../geo/marsCoordinates.ts";
import type { MarsCoordinate, PlanRouteResponse } from "../types/api.ts";

const lineStyles = [
  new Style({ stroke: new Stroke({ color: "#101820", width: 7 }) }),
  new Style({ stroke: new Stroke({ color: "#ffe292", width: 4, lineDash: [9, 6] }) }),
];
const markerStyles = Object.fromEntries((["start", "goal"] as const).map((kind) => [kind, new Style({
  image: new Circle({ radius: 12, fill: new Fill({ color: kind === "start" ? "#77edc2" : "#ffb59e" }), stroke: new Stroke({ color: "#101820", width: 2 }) }),
  text: new Text({ text: kind === "start" ? "S" : "G", font: "bold 13px sans-serif", fill: new Fill({ color: "#101820" }) }),
  zIndex: 2,
})]));

export function createRouteOverlay() {
  const source = new VectorSource({ wrapX: false });
  const layer = new VectorLayer({
    source,
    style: (feature) => feature.get("kind") === "route" ? lineStyles : feature.get("kind") === "waypoint" ? new Style({
      image: new Circle({ radius: 10, fill: new Fill({ color: "#b7b9ff" }), stroke: new Stroke({ color: "#101820", width: 2 }) }),
      text: new Text({ text: feature.get("label"), font: "bold 12px sans-serif", fill: new Fill({ color: "#101820" }) }), zIndex: 2,
    }) : markerStyles[feature.get("kind") as "start" | "goal"],
  });
  layer.setZIndex(10);
  return { source, layer };
}

export function updateRouteOverlay(source: VectorSource, start: MarsCoordinate | null, goal: MarsCoordinate | null, result: PlanRouteResponse | null, waypoints: MarsCoordinate[] = [], mapAlignment: "verified" | "unverified" | undefined = undefined) {
  source.clear();
  if (result && (result.source === "mock" || mapAlignment === "verified")) {
    source.addFeature(new Feature({ kind: "route", geometry: new MultiLineString(routeToMapSegments(result.route, "wmts-display")) }));
  }
  waypoints.forEach((point, index) => source.addFeature(new Feature({ kind: "waypoint", label: `W${index + 1}`,
    geometry: new Point(apiCoordinateToMapView(point, "wmts-display")) })));
  for (const [kind, point] of [["start", start], ["goal", goal]] as const) {
    if (point) source.addFeature(new Feature({ kind, geometry: new Point(apiCoordinateToMapView(point, "wmts-display")) }));
  }
}
