"""Bounded visual previews of local rasters; never used as route cost inputs."""
from functools import lru_cache
from pathlib import Path
import math

from app.api.errors import ApiProblem
from app.planning.grid import source_bounds

RASTERS = {
    'dem_surface': ('M20 DEM elevation', 'M20_JezeroCrater_CTXDEM_20m.tif'),
    'thermal': ('THEMIS daytime visual context', 'Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif'),
    'thermal_night': ('THEMIS nighttime visual context', 'THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018.tif'),
}
GEOLOGY_ARCHIVE=Path(__file__).resolve().parents[3]/'data/cache/a4-geology/sim3464/sim3464_database.zip'


def geology():
    if not GEOLOGY_ARCHIVE.is_file():
        raise ApiProblem(404,'MAP_LAYER_UNAVAILABLE','Local SIM 3464 geology archive is missing.')
    try:
        stat=GEOLOGY_ARCHIVE.stat()
        return _geology(str(GEOLOGY_ARCHIVE),stat.st_mtime_ns,stat.st_size)
    except (OSError,ValueError,RuntimeError,ImportError):
        raise ApiProblem(503,'MAP_LAYER_UNAVAILABLE','Local geology polygons could not be loaded.') from None


@lru_cache(maxsize=1)
def _geology(path,mtime,size):
    import numpy as np
    from pyproj import Transformer
    from shapely.ops import transform
    from shapely.geometry import mapping
    from app.agents.a4.geology import extract_vectors,read_catalog
    archive=Path(path)
    gdb,prj,manifest=extract_vectors(archive,archive.parent/'map-vectors')
    catalog=read_catalog(gdb,prj,version=manifest['archive']['sha256'],provenance_ref='USGS SIM 3464')
    inverse=Transformer.from_crs(catalog.crs,catalog.crs.geodetic_crs,always_xy=True)
    def display(x,y,z=None):
        lon,lat=inverse.transform(x,y)
        b=3396190*(1-1/169.894447223612)
        return lon,np.degrees(np.arctan((3396190/b)**2*np.tan(np.radians(lat))))
    return dict(type='FeatureCollection',features=[dict(type='Feature',
        properties=item.reference.model_dump(),geometry=mapping(transform(display,item.geometry.simplify(20,preserve_topology=True))))
        for item in catalog.polygons],source='USGS SIM 3464',
        notice='Regional geology at 1:75,000; source reports approximate 100–200 m offsets. Display simplified to 20 m; no alignment shift applied.')


def graphic(latitude):
    b = 3396190 * (1 - 1 / 169.894447223612)
    return math.degrees(math.atan((3396190 / b) ** 2 * math.tan(math.radians(latitude))))


def catalog(planning):
    result=[]
    for identifier,(label,filename) in RASTERS.items():
        path=_path(planning,identifier)
        available=path is not None and path.is_file() and planning.grid is not None
        result.append(dict(id=identifier,label=label,available=available,
            image_url=f'/api/v1/map/layers/{identifier}.png' if available else None,
            extent=_extent(planning) if available else None,
            notice='Local raster visual preview; stretched values are not calibrated environmental risk.'))
    return dict(layers=result)


def _path(planning,identifier):
    if identifier not in RASTERS:
        raise ApiProblem(404,'MAP_LAYER_NOT_FOUND','Unknown map layer.')
    if planning.grid is None: return None
    if identifier=='dem_surface': return planning.grid.source_path
    return planning.grid.source_path.parent / RASTERS[identifier][1]


def _extent(planning):
    bounds=source_bounds(planning.grid)
    return [bounds.west,graphic(bounds.south),bounds.east,graphic(bounds.north)]


def image(planning,identifier):
    path=_path(planning,identifier)
    if path is None or not path.is_file():
        raise ApiProblem(404,'MAP_LAYER_UNAVAILABLE','This local raster is unavailable.')
    bounds=source_bounds(planning.grid)
    try:
        stat=path.stat()
        return _render(str(path),stat.st_mtime_ns,stat.st_size,(bounds.west,bounds.east,bounds.south,bounds.north))
    except (OSError,ValueError,RuntimeError):
        raise ApiProblem(503,'MAP_LAYER_UNAVAILABLE','The raster preview could not be generated; planning remains available.') from None


@lru_cache(maxsize=6)
def _render(path,mtime,size,bounds):
    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.windows import from_bounds, Window
    from rasterio.warp import reproject, transform_bounds, Resampling
    from rasterio.transform import from_bounds as geo_transform
    # Every image covers the DEM footprint. Sampling is bounded even for a
    # multi-gigabyte global raster; only the local window is read/downsampled.
    west,east,south,north=bounds
    target_crs='+proj=longlat +R=3396190 +no_defs'
    n=512
    target=np.full((n,n),np.nan,dtype='float32')
    with rasterio.open(path) as src:
        box=transform_bounds(target_crs,src.crs,west,south,east,north,densify_pts=21)
        window=from_bounds(*box,src.transform).round_offsets().round_lengths()
        window=window.intersection(Window(0,0,src.width,src.height))
        sample=src.read(1,window=window,out_shape=(n,n),masked=True,resampling=Resampling.bilinear).astype('float32')
        native_transform=src.window_transform(window)*src.transform.scale(window.width/n,window.height/n)
        reproject(sample.filled(np.nan),target,src_transform=native_transform,src_crs=src.crs,src_nodata=np.nan,
            dst_transform=geo_transform(west,south,east,north,n,n),dst_crs=target_crs,dst_nodata=np.nan,resampling=Resampling.bilinear)
    valid=np.isfinite(target)
    gray=np.zeros_like(target,dtype='uint8')
    if valid.any():
        lo,hi=np.percentile(target[valid],[2,98])
        gray[valid]=np.clip((target[valid]-lo)/max(float(hi-lo),1e-6)*255,0,255).astype('uint8')
    with MemoryFile() as mem:
        with mem.open(driver='PNG',width=n,height=n,count=2,dtype='uint8') as out:
            out.write(gray,1); out.write(valid.astype('uint8')*255,2)
        return mem.read()
