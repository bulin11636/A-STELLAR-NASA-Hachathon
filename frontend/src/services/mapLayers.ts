import { apiRequest } from './apiClient.ts';
export interface RasterLayer { id:string; label:string; available:boolean; image_url:string|null; extent:[number,number,number,number]|null; notice:string }
export function getMapLayers(signal?:AbortSignal) {
  return apiRequest('/api/v1/map/layers',value=>{
    const data=value as {layers:RasterLayer[]};
    if (!Array.isArray(data?.layers)) throw new Error('Invalid map layer catalog.');
    for (const layer of data.layers) {
      if (!['dem_surface','thermal','thermal_night'].includes(layer.id) || typeof layer.available!=='boolean') throw new Error('Invalid map layer.');
      if (layer.available && (layer.image_url!==`/api/v1/map/layers/${layer.id}.png` || !Array.isArray(layer.extent) ||
        layer.extent.length!==4 || !layer.extent.every(Number.isFinite) || layer.extent[0]>=layer.extent[2] || layer.extent[1]>=layer.extent[3])) throw new Error('Invalid raster extent.');
    }
    return data.layers;
  },{signal});
}
