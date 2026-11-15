import { boundingExtent } from "ol/extent.js";
import { apiCoordinateToMapView } from "../geo/marsCoordinates.ts";
import type { MarsCoordinate } from "../types/api.ts";

export function missionViewport(points: MarsCoordinate[], minimumSpanDegrees: number): [number, number, number, number] | null {
  if (!points.length) return null;
  const extent = boundingExtent(points.map((point) => apiCoordinateToMapView(point, "wmts-display")));
  const centerX = (extent[0] + extent[2]) / 2;
  const centerY = (extent[1] + extent[3]) / 2;
  const halfSpan = Math.max(minimumSpanDegrees, extent[2] - extent[0], extent[3] - extent[1]) / 2;
  return [centerX - halfSpan, centerY - halfSpan, centerX + halfSpan, centerY + halfSpan];
}
