"""A deliberately narrow, auditable DEM ingestion profile; no reprojection guesses."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING
from pydantic import Field
from app.contracts.api import ContractModel, MarsCoordinate, COORDINATE_SYSTEM
from app.contracts.routes import Limits, GridMetadata, Bounds
from app.api.errors import ApiProblem

VERSION = 'dem-conservative-adaptive-v2'

if TYPE_CHECKING:
    import numpy as np


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def transform_point(transform, point):
    """Apply the declared affine coefficients without version-specific operators."""
    x,y = point
    return (transform.a*x+transform.b*y+transform.c,
            transform.d*x+transform.e*y+transform.f)


class PlanningProfile(ContractModel):
    dem: str
    dataset_id: str
    roi_id: str
    window: tuple[int, int, int, int]  # column offset, row offset, width, height
    vertical_units: str  # explicit host assertion, not inferred from filename
    vertical_units_evidence: str = Field(min_length=1)
    source_url: str | None = None
    instrument: str | None = None
    mission: str | None = None
    acquisition_time: str | None = None
    registration_controls: str | None = None
    wmts_layer: str = 'Mars_MGS_MOLA_ClrShade_merge_global_463m'
    slope_threshold_deg: float = Field(default=15, gt=0, lt=90)
    terrain_weight: float = Field(default=4, ge=0, le=100)
    dynamic_windowing: bool = True
    adaptive_resolution: bool = True
    min_resolution_factor: int = Field(default=1, ge=1, le=32)
    max_resolution_factor: int = Field(default=16, ge=1, le=32)
    window_margin_cells: int = Field(default=24, ge=2, le=256)
    limits: Limits = Limits(max_grid_cells=262144, max_expanded_nodes=200000, max_elapsed_seconds=5)


@dataclass
class TerrainGrid:
    profile: PlanningProfile
    source_path: Path
    source_stat: tuple
    source_hash: str
    metadata: GridMetadata
    bounds: Bounds
    elevation: np.ndarray
    slope: np.ndarray
    coverage: np.ndarray
    unknown: np.ndarray
    blocked: np.ndarray
    transform: object
    forward: object
    inverse: object
    inventory: dict

    @property
    def allowed(self):
        return self.coverage & ~self.unknown & ~self.blocked

    def ensure_unchanged(self):
        if fingerprint(self.source_path) != self.source_stat:
            raise ApiProblem(503, 'PLANNING_UNAVAILABLE', 'DEM changed since grid construction; rebuild the application grid.')
        if 'profile_path' in self.inventory and fingerprint(Path(self.inventory['profile_path'])) != tuple(self.inventory['profile_stat']):
            raise ApiProblem(503, 'PLANNING_UNAVAILABLE', 'The planning profile changed; restart the backend to apply it consistently.')

    def xy(self, point):
        return self.forward.transform(point.longitude, point.latitude, errcheck=True)

    def wire(self, x, y):
        lon, lat = self.inverse.transform(x, y, errcheck=True)
        return MarsCoordinate(longitude=lon % 360, latitude=lat)

    def cell(self, point):
        x, y = self.xy(point)
        col, row = transform_point(~self.transform,(x,y))
        # Native pixel areas are half-open: west/north included, east/south excluded.
        if not (math.isfinite(col) and math.isfinite(row) and 0 <= col < self.metadata.width and 0 <= row < self.metadata.height):
            raise ApiProblem(400, 'OUTSIDE_PLANNING_COVERAGE', 'An endpoint is outside the configured planning footprint.')
        return math.floor(row), math.floor(col)

    def center(self, cell):
        r, c = cell
        return transform_point(self.transform,(c+.5,r+.5))

    def arrays(self):
        import numpy as np
        return dict(elevation=self.elevation, slope=self.slope, coverage=self.coverage,
                    unknown=self.unknown, blocked=self.blocked,
                    shortest_cost=np.ones_like(self.slope),
                    safest_cost=1+self.profile.terrain_weight*(self.slope/self.profile.slope_threshold_deg)**2)


def fingerprint(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def read_native_terrain(src, col, row, width, height, threshold):
    """Read a bounded native window with the same derivative halo at every scale."""
    import numpy as np
    from rasterio.windows import Window
    raw = src.read(1, window=Window(col-1, row-1, width+2, height+2), masked=True)
    z = np.asarray(raw.data, dtype=np.float64)*src.scales[0]+src.offsets[0]
    valid = ~np.ma.getmaskarray(raw) & np.isfinite(z)
    stencil = valid[1:-1,1:-1] & valid[:-2,1:-1] & valid[2:,1:-1] & valid[1:-1,:-2] & valid[1:-1,2:]
    with np.errstate(invalid='ignore', over='ignore'):
        gx = (z[1:-1,2:]-z[1:-1,:-2])/(2*src.transform.a)
        gy = (z[2:,1:-1]-z[:-2,1:-1])/(2*abs(src.transform.e))
        slope = np.degrees(np.arctan(np.hypot(gx,gy)))
    unknown = ~stencil | ~np.isfinite(slope)
    slope[unknown] = 0
    coverage = valid[1:-1,1:-1]
    elevation = z[1:-1,1:-1].copy()
    elevation[~coverage] = 0
    return elevation, slope, coverage, unknown, slope > threshold


def aggregate_terrain(src, window, factor, threshold):
    """Conservative block reduction, never average away a native hazard.

    Only complete blocks are traversable. Streaming tiles bound native read
    allocations independently of the overall source footprint.
    """
    import numpy as np
    col, row, width, height = window
    h, w = math.ceil(height/factor), math.ceil(width/factor)
    outputs = [np.zeros((h,w), dtype=dtype) for dtype in (float,float,bool,bool,bool)]
    outputs[3][:] = True
    # At most 512 x 512 native cells plus the derivative halo per source read.
    tile = max(1, 512//factor)
    for r in range(0, height//factor, tile):
        for c in range(0, width//factor, tile):
            nh, nw = min(tile, height//factor-r), min(tile, width//factor-c)
            native = read_native_terrain(src,col+c*factor,row+r*factor,nw*factor,nh*factor,threshold)
            for index, (array, reduce) in enumerate(zip(native, ('mean','max','all','any','any'))):
                blocks = array.reshape(nh, factor, nw, factor)
                outputs[index][r:r+nh,c:c+nw] = getattr(blocks, reduce)(axis=(1,3))
    return outputs


def load_grid(profile_path, *, window=None, reference=None, dataset_root=None, resolution_factor=1, policy=None):
    # Only computed mode imports these dependencies; ordinary API/mock imports stay light.
    import numpy as np
    import rasterio
    from rasterio.windows import Window
    from pyproj import CRS, Transformer
    path = Path(profile_path).expanduser().resolve()
    profile_stat = fingerprint(path)
    p = policy or PlanningProfile.model_validate_json(path.read_text())
    if window is not None:
        p = p.model_copy(update={'window': window, 'roi_id': p.roi_id+'-crop-'+hashlib.sha256(str(window).encode()).hexdigest()[:12]})
    root = Path(dataset_root or os.environ.get('A_STELLAR_DATASET_DIR', str(path.parent))).expanduser().resolve()
    dem = (root / p.dem).resolve()
    before = fingerprint(dem)
    # Hash once during grid construction, outside requests. Never reuse cached grids on stat changes.
    if reference is not None:
        reference.ensure_unchanged()
        if dem != reference.source_path or before != reference.source_stat:
            raise ApiProblem(503, 'PLANNING_UNAVAILABLE', 'The configured DEM changed.')
    sha = reference.source_hash if reference is not None else digest(dem)
    with rasterio.open(dem) as src:
        crs = CRS.from_wkt(src.crs.to_wkt()) if src.crs else None
        if (crs is None or not crs.is_projected or 'mars' not in crs.geodetic_crs.name.lower()
            or crs.prime_meridian.longitude != 0
            or crs.ellipsoid.inverse_flattening != 0 or not 3380000 <= crs.ellipsoid.semi_major_metre <= 3400000
            or any(axis.unit_name != 'metre' for axis in crs.axis_info)
            or crs.coordinate_operation.method_name != 'Equidistant Cylindrical (Spherical)'):
            raise ValueError('Only verified spherical Mars equirectangular metre CRSs are supported')
        t = src.transform
        if not all(math.isfinite(v) for v in tuple(t)) or t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0:
            raise ValueError('Rotated, skewed or reversed DEM axes are unsupported')
        if p.vertical_units != 'm':
            raise ValueError('Explicit metre elevation units are required')
        if not math.isfinite(src.scales[0]) or not math.isfinite(src.offsets[0]) or src.scales[0] == 0:
            raise ValueError('A finite nonzero elevation scale and finite offset are required')
        col, row, width, height = p.window
        factor = resolution_factor
        if (type(factor) is not int or not 1 <= factor <= p.max_resolution_factor
            or width < 1 or height < 1 or math.ceil(width/factor)*math.ceil(height/factor) > p.limits.max_grid_cells):
            raise ApiProblem(503, 'PLANNING_LIMIT_EXCEEDED', 'The configured grid exceeds the allocation limit.')
        if col < 1 or row < 1 or col+width >= src.width or row+height >= src.height:
            raise ValueError('The planning window requires a one-pixel source halo')
        elevation,slope,coverage,unknown,blocked = (read_native_terrain(src,col,row,width,height,p.slope_threshold_deg)
            if factor == 1 else aggregate_terrain(src,p.window,factor,p.slope_threshold_deg))
        from affine import Affine
        native_transform = src.window_transform(Window(col,row,width,height))
        tr = Affine(native_transform.a*factor,native_transform.b*factor,native_transform.c,
                    native_transform.d*factor,native_transform.e*factor,native_transform.f)
        grid_h, grid_w = elevation.shape
        forward = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
        inverse = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        corners = [inverse.transform(*transform_point(tr,(c,r))) for c,r in [(0,0),(grid_w,0),(grid_w,grid_h),(0,grid_h)]]
        grid_id = 'grid-'+hashlib.sha256((sha+p.model_dump_json()+str(factor)+VERSION).encode()).hexdigest()[:24]
        metadata = GridMetadata(grid_id=grid_id, source_crs=crs.to_wkt(), planning_crs=crs.to_wkt(),
            wire_convention=COORDINATE_SYSTEM, affine=tuple(tr)[:6],
            affine_order='a,b,c,d,e,f; x=a*column+b*row+c; y=d*column+e*row+f',
            width=grid_w,height=grid_h, source_resolution=(t.a,abs(t.e)),planning_resolution_m=(t.a*factor,abs(t.e)*factor),
            vertical_units='m',vertical_scale=src.scales[0],vertical_offset=src.offsets[0],nodata=str(src.nodata),
            mask_artifact_ids={k:grid_id+':'+k for k in ['coverage','unknown','blocked']})
        inventory = dict(source_shape=src.shape, source_window=p.window, halo_pixels=1, source_tags=src.tags(),
            resolution_factor=factor, aggregation='none' if factor==1 else 'all native cells must be traversable; maximum native slope; partial edge blocks unknown',
            profile_path=str(path), profile_stat=profile_stat,
            band_units=src.units, vertical_units_evidence=p.vertical_units_evidence, source_stat=before,
            source_crs=crs.to_wkt(), source_transform=tuple(t)[:6], source_nodata=str(src.nodata),
            radius_m=crs.ellipsoid.semi_major_metre, source_resolution=[t.a,abs(t.e)],
            geometry='Native spherical equirectangular planar distances; projection distortion is retained. No 3D or ground-distance claim.',
            latitude='Planetocentric on the declared sphere; east-positive longitude, prime meridian zero',
            resampling='none' if factor==1 else 'conservative block aggregation after native derivatives', units_warning='Host-asserted vertical units; input authenticity is not independently certified.')
    if fingerprint(dem) != before or fingerprint(path) != profile_stat:
        raise ValueError('DEM changed during ingestion')
    return TerrainGrid(p,dem,before,sha,metadata,
        Bounds(west=min(x for x,y in corners),east=max(x for x,y in corners),south=min(y for x,y in corners),north=max(y for x,y in corners)),
        elevation,slope,coverage,unknown,blocked,tr,forward,inverse,inventory)


def source_bounds(grid):
    from affine import Affine
    tr = Affine(*grid.inventory['source_transform'])
    height, width = grid.inventory['source_shape']
    # Derivatives need a one-pixel halo. Advertise the supported interior.
    points = [grid.inverse.transform(*transform_point(tr,(c,r))) for c,r in
              [(1,1),(width-1,1),(width-1,height-1),(1,height-1)]]
    return Bounds(west=min(x for x,y in points), east=max(x for x,y in points),
                  south=min(y for x,y in points), north=max(y for x,y in points))


def regional_grid(profile_path, base, dataset_root=None):
    height, width = base.inventory['source_shape']
    factor = base.profile.min_resolution_factor
    while math.ceil((width-2)/factor)*math.ceil((height-2)/factor) > base.profile.limits.max_grid_cells:
        factor += 1
    if factor > base.profile.max_resolution_factor or (factor > 1 and not base.profile.adaptive_resolution):
        raise ApiProblem(503,'PLANNING_LIMIT_EXCEEDED','The source exceeds the configured adaptive-resolution limits.')
    return load_grid(profile_path,window=(1,1,width-2,height-2),reference=base,
                     dataset_root=dataset_root,resolution_factor=factor,policy=base.profile)


def grid_for_request(profile_path, base, request, dataset_root=None, regional_reference=None):
    from affine import Affine
    if not base.profile.dynamic_windowing:
        factor=base.profile.min_resolution_factor
        if factor==1: return base
        return load_grid(profile_path,reference=base,dataset_root=dataset_root,resolution_factor=factor,policy=base.profile)
    points = [request.start, *request.waypoints, request.goal]
    try:
        for point in points:
            base.cell(point)
        if base.inventory.get('resolution_factor',1)>=base.profile.min_resolution_factor and base.metadata.width*base.metadata.height<=base.profile.limits.max_grid_cells:
            return base
    except ApiProblem:
        pass
    tr = Affine(*base.inventory['source_transform'])
    height, width = base.inventory['source_shape']
    cells = [transform_point(~tr,base.xy(point)) for point in points]
    if any(not (math.isfinite(c) and math.isfinite(r) and 1 <= c < width-1 and 1 <= r < height-1) for c,r in cells):
        raise ApiProblem(400, 'OUTSIDE_PLANNING_COVERAGE', 'A route stop is outside the supported DEM source footprint.')
    margin = base.profile.window_margin_cells
    left = max(1, math.floor(min(c for c,r in cells))-margin)
    top = max(1, math.floor(min(r for c,r in cells))-margin)
    right = min(width-1, math.floor(max(c for c,r in cells))+margin+1)
    bottom = min(height-1, math.floor(max(r for c,r in cells))+margin+1)
    factor = base.profile.min_resolution_factor
    while math.ceil((right-left)/factor)*math.ceil((bottom-top)/factor) > base.profile.limits.max_grid_cells:
        factor += 1
    if factor > base.profile.min_resolution_factor and base.profile.adaptive_resolution:
        # Regional searches include the whole supported source, so a tight
        # endpoint corridor cannot cut off a crater-scale detour.
        if regional_reference is not None:
            regional_reference.ensure_unchanged()
            return regional_reference
        return regional_grid(profile_path,base,dataset_root)
    if factor > base.profile.max_resolution_factor or (factor > 1 and not base.profile.adaptive_resolution):
        raise ApiProblem(503, 'PLANNING_LIMIT_EXCEEDED', 'The route exceeds the configured grid and adaptive-resolution limits.')
    return load_grid(profile_path, window=(left,top,right-left,bottom-top), reference=base,
                     dataset_root=dataset_root, resolution_factor=factor,policy=base.profile)
