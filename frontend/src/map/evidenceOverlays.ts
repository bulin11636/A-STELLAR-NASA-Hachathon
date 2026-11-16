import Feature from "ol/Feature.js";
import LineString from "ol/geom/LineString.js";
import Point from "ol/geom/Point.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { Circle, Fill, Stroke, Style, Text } from "ol/style.js";
import { JEZERO_EVIDENCE_DEMO, type RoverStopFixture, type ScienceFixture } from "../fixtures/jezeroEvidenceDemo.ts";
import { apiCoordinateToMapView } from "../geo/marsCoordinates.ts";

export type SelectedEvidence =
  | { kind: "science"; item: ScienceFixture }
  | { kind: "rover_stop"; item: RoverStopFixture };

const scienceStyle = new Style({
  image: new Circle({ radius: 7, fill: new Fill({ color: "#a9d8ff" }), stroke: new Stroke({ color: "#10212e", width: 2 }) }),
  text: new Text({ text: "✦", font: "bold 12px sans-serif", fill: new Fill({ color: "#10212e" }) }),
});
const stopStyle = new Style({
  image: new Circle({ radius: 5, fill: new Fill({ color: "#dbb0ff" }), stroke: new Stroke({ color: "#20142c", width: 2 }) }),
});
const traverseStyle = new Style({ stroke: new Stroke({ color: "#dcb0ff", width: 3, lineDash: [5, 4] }) });

export function createEvidenceOverlays() {
  const scienceSource = new VectorSource({ wrapX: false });
  const traverseSource = new VectorSource({ wrapX: false });
  const stopSource = new VectorSource({ wrapX: false });
  const stopLayer = new VectorLayer({ source: stopSource, style: stopStyle, zIndex: 7 });
  const scienceLayer = new VectorLayer({ source: scienceSource, style: (feature) => feature.get("kind") === "science" ? scienceStyle : stopStyle });
  const traverseLayer = new VectorLayer({ source: traverseSource, style: traverseStyle });
  scienceLayer.setZIndex(7);
  traverseLayer.setZIndex(6);

  for (const item of JEZERO_EVIDENCE_DEMO.scienceSites) {
    scienceSource.addFeature(new Feature({ kind: "science", evidence: item, geometry: new Point(apiCoordinateToMapView(item, "wmts-display")) }));
  }
  for (const item of JEZERO_EVIDENCE_DEMO.roverStops) {
    stopSource.addFeature(new Feature({ kind: "rover_stop", evidence: item, geometry: new Point(apiCoordinateToMapView(item, "wmts-display")) }));
  }
  for (const item of JEZERO_EVIDENCE_DEMO.traverse) {
    traverseSource.addFeature(new Feature({
      kind: "traverse", evidence: item,
      geometry: new LineString(item.points.map((point) => apiCoordinateToMapView(point, "wmts-display"))),
    }));
  }
  return { scienceLayer, traverseLayer, stopLayer };
}
