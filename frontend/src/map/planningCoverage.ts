import Feature from 'ol/Feature.js';
import Polygon from 'ol/geom/Polygon.js';
import VectorLayer from 'ol/layer/Vector.js';
import VectorSource from 'ol/source/Vector.js';
import { Fill, Stroke, Style } from 'ol/style.js';
import { apiCoordinateToMapView } from '../geo/marsCoordinates.ts';
import type { MarsCoordinate, PlanRouteRequest, PlanningInfo, PlanningRegion } from '../types/api.ts';

export function planningBounds(region: PlanningRegion | null | undefined) {
  const p=region?.routing_mode==='computed' ? region.planning : null;
  return p ? (p.dynamic_windowing ? p.source_bounds ?? null : p.bounds) : null;
}

export function coverageError(region: PlanningRegion | null | undefined, request: PlanRouteRequest): string | null {
  const b=planningBounds(region);
  if (!b) return null;
  const stops=[request.start,...(request.waypoints ?? []),request.goal];
  for (let i=0;i<stops.length;i++) {
    const p=stops[i];
    if (p.longitude<b.west || p.longitude>=b.east || p.latitude<=b.south || p.latitude>b.north) {
      const label=i===0 ? 'Start' : i===stops.length-1 ? 'Goal' : `Waypoint ${i}`;
      return `${label} is outside the supported DEM boundary. Select it inside the cyan outline; the small dashed example window is not the regional limit.`;
    }
  }
  return null;
}

function polygon(b: PlanningInfo['bounds']) {
  return new Polygon([[[b.west,b.south],[b.east,b.south],[b.east,b.north],[b.west,b.north],[b.west,b.south]]
    .map(([longitude,latitude])=>apiCoordinateToMapView({longitude,latitude} as MarsCoordinate,'wmts-display'))]);
}

export function createCoverageLayer(bounds: PlanningInfo['bounds'], example=false) {
  return new VectorLayer({source:new VectorSource({wrapX:false,features:[new Feature({geometry:polygon(bounds)})]}),
    style:new Style({stroke:new Stroke({color:example ? '#ffce82' : '#65e5eb',width:2,lineDash:example ? [6,5] : undefined}),
      fill:new Fill({color:example ? 'rgba(255,206,130,0.05)' : 'rgba(101,229,235,0.025)'})}),zIndex:5});
}
