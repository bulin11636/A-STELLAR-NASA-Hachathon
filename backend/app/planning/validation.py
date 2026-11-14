"""Independent segment checks using closed cell-box intersection, including corner touches."""
import math
import numpy as np
from app.api.errors import ApiProblem
from app.planning.grid import transform_point


def intersects_box(a, b, left, top, right, bottom):
    lo, hi = 0.0, 1.0
    for x, delta, low, high in ((a[0],b[0]-a[0],left,right),(a[1],b[1]-a[1],top,bottom)):
        if abs(delta) < 1e-14:
            if x < low-1e-10 or x > high+1e-10:
                return False
        else:
            u,v = (low-x)/delta, (high-x)/delta
            lo,hi = max(lo,min(u,v)),min(hi,max(u,v))
            if lo > hi+1e-10:
                return False
    return True


def validate_polyline(grid, points, expected_hash):
    grid.ensure_unchanged()
    if grid.source_hash != expected_hash:
        raise ValueError('Source/version changed')
    pixels = [transform_point(~grid.transform,xy) for xy in points]
    h,w = grid.allowed.shape
    allowed = grid.allowed
    for c,r in pixels:
        if not (np.isfinite([c,r]).all() and 0 <= c < w and 0 <= r < h):
            raise ValueError('Route leaves ROI')
    touched = set()
    distance = 0.0
    for a,b,xy1,xy2 in zip(pixels,pixels[1:],points,points[1:]):
        # Search emits adjacent centers, and connectors stay in one endpoint cell.
        # Reject arbitrary long segments before enumerating boxes (bounded validation work).
        if max(abs(a[0]-b[0]),abs(a[1]-b[1])) > 1.000001:
            raise ValueError('Nonadjacent route vertices')
        for r in range(max(0,math.floor(min(a[1],b[1]))-1),min(h,math.floor(max(a[1],b[1]))+2)):
            for c in range(max(0,math.floor(min(a[0],b[0]))-1),min(w,math.floor(max(a[0],b[0]))+2)):
                if intersects_box(a,b,c,r,c+1,r+1):
                    if not allowed[r,c]:
                        raise ApiProblem(400,'ENDPOINT_NOT_TRAVERSABLE','A route segment touches blocked or unknown terrain.')
                    touched.add((r,c))
        distance += math.dist(xy1,xy2)
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError('Invalid route length')
    return distance, sorted(touched)


def validate_native_polyline(grid, points):
    """Independently re-read the native source along an aggregated-grid route.

    Every touched native pixel is checked with the original derivative stencil.
    Source reads and intersection work are bounded by the aggregation factor,
    rather than allocating a full-resolution crater-wide grid.
    """
    import rasterio
    from affine import Affine
    from app.planning.grid import read_native_terrain
    grid.ensure_unchanged()
    transform = Affine(*grid.inventory['source_transform'])
    pixels = [transform_point(~transform,xy) for xy in points]
    factor = grid.inventory.get('resolution_factor',1)
    touched = set()
    with rasterio.open(grid.source_path) as src:
        for a,b in zip(pixels,pixels[1:]):
            if max(abs(a[0]-b[0]),abs(a[1]-b[1])) > factor+1e-5:
                raise ValueError('Unbounded native validation segment')
            left, top = math.floor(min(a[0],b[0]))-1, math.floor(min(a[1],b[1]))-1
            right, bottom = math.floor(max(a[0],b[0]))+2, math.floor(max(a[1],b[1]))+2
            left, top = max(1,left), max(1,top)
            right, bottom = min(src.width-1,right), min(src.height-1,bottom)
            if left >= right or top >= bottom:
                raise ValueError('Native validation leaves supported source')
            _,_,coverage,unknown,blocked = read_native_terrain(src,left,top,right-left,bottom-top,grid.profile.slope_threshold_deg)
            allowed = coverage & ~unknown & ~blocked
            for r in range(top,bottom):
                for c in range(left,right):
                    if intersects_box(a,b,c,r,c+1,r+1):
                        if not allowed[r-top,c-left]:
                            raise ApiProblem(400,'ENDPOINT_NOT_TRAVERSABLE','A route segment touches blocked or unknown native terrain.')
                        touched.add((r,c))
    grid.ensure_unchanged()
    return dict(status='passed',method='closed native pixel-box intersection with re-read central derivatives',
                source_sha256=grid.source_hash,source_resolution_m=list(grid.metadata.source_resolution),
                touched_native_cells=len(touched))
