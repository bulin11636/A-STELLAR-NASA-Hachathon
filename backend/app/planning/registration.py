"""Independent WMTS/wire/DEM controls; round trips alone never verify a map."""
import hashlib
import json
import math
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET

from pydantic import Field, model_validator
from app.contracts.base import ContractModel
from app.contracts.api import MarsCoordinate
from app.contracts.registration import ControlResidual, MapRegistration
from app.planning.grid import transform_point

SEMIMAJOR=3396190.0
SEMIMINOR=SEMIMAJOR*(1-1/169.894447223612)
NASA_CRS='urn:ogc:def:crs:EPSG::104905'
NASA_LAYER='Mars_MGS_MOLA_ClrShade_merge_global_463m'


class Observation(ContractModel):
    control_id: str = Field(min_length=1,max_length=100)
    wire: MarsCoordinate
    dem_pixel: tuple[float,float]
    wmts_coordinate: tuple[float,float]
    wire_uncertainty_m: float = Field(ge=0,le=50)
    feature_uncertainty_m: float = Field(ge=0,le=50)
    wmts_resolution_m: float = Field(gt=0,le=10000)
    wmts_matrix_id: str


class ControlSet(ContractModel):
    schema_version: Literal['1']
    data_kind: Literal['observed','synthetic']
    measurement_method: Literal['independent_feature_measurement','synthetic_fixture']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    wmts_layer: str
    wmts_matrix_set: str
    wmts_crs: Literal['urn:ogc:def:crs:EPSG::104905']
    latitude_type: Literal['planetographic']
    semi_major_m: Literal[3396190.0]
    inverse_flattening: Literal[169.894447223612]
    capabilities_file: str
    capabilities_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    measurement_file: str
    measurement_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    observations: list[Observation] = Field(min_length=4,max_length=64)

    @model_validator(mode='after')
    def unique_controls(self):
        if (self.data_kind=='synthetic')!=(self.measurement_method=='synthetic_fixture'): raise ValueError('Observed and synthetic measurement provenance cannot be mixed.')
        if len({o.control_id for o in self.observations})!=len(self.observations): raise ValueError('Duplicate controls')
        if len({o.dem_pixel for o in self.observations})!=len(self.observations): raise ValueError('Repeated feature positions')
        return self


def planetographic(latitude):
    if abs(latitude)==90: return latitude
    return math.degrees(math.atan((SEMIMAJOR/SEMIMINOR)**2*math.tan(math.radians(latitude))))


def planetocentric(latitude):
    if abs(latitude)==90: return latitude
    return math.degrees(math.atan((SEMIMINOR/SEMIMAJOR)**2*math.tan(math.radians(latitude))))


def hull(points):
    points=sorted(set(points))
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower=[];upper=[]
    for p in points:
        while len(lower)>1 and cross(lower[-2],lower[-1],p)<=0: lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>1 and cross(upper[-2],upper[-1],p)<=0: upper.pop()
        upper.append(p)
    return lower[:-1]+upper[:-1]


def covered(polygon,point,tolerance=1e-6):
    return len(polygon)>=3 and all((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])>=-tolerance
        for a,b in zip(polygon,polygon[1:]+polygon[:1]))


def asset(root,name,expected):
    p=(root/name).resolve()
    if Path(name).is_absolute() or not p.is_relative_to(root.resolve()) or p.is_symlink(): raise ValueError('Unbounded evidence asset')
    if p.stat().st_size>2_000_000: raise ValueError('Oversized evidence asset')
    content=p.read_bytes()
    if hashlib.sha256(content).hexdigest()!=expected: raise ValueError('Evidence integrity failure')
    return content


def validate_controls(grid,path,route,*,allow_synthetic=False):
    # Surface the requested NASA target even before an operator has supplied
    # controls. It makes a pending registration auditable without implying that
    # the DEM and imagery align.
    result=MapRegistration(source_sha256=grid.source_hash,wmts_layer=grid.profile.wmts_layer,wmts_crs=NASA_CRS)
    if path is None:
        return result.model_copy(update={'reasons':['Independent NASA WMTS/wire/DEM feature measurements have not been configured.']})
    try:
        if path.is_symlink() or path.stat().st_size>1_000_000: raise ValueError('Invalid control input')
        content=path.read_bytes();data=ControlSet.model_validate_json(content)
        updates=dict(controls_sha256=hashlib.sha256(content).hexdigest(),capabilities_sha256=data.capabilities_sha256,
            measurement_sha256=data.measurement_sha256,wmts_layer=data.wmts_layer,wmts_crs=data.wmts_crs,synthetic=data.data_kind=='synthetic')
        result=result.model_copy(update=updates)
        if data.source_sha256!=grid.source_hash or data.wmts_layer!=grid.profile.wmts_layer: raise ValueError('Source/layer mismatch')
        if data.data_kind=='synthetic' and not (allow_synthetic and grid.profile.dataset_id.startswith('synthetic')):
            raise ValueError('Synthetic controls cannot verify production imagery')
        xml=ET.fromstring(asset(path.parent,data.capabilities_file,data.capabilities_sha256))
        asset(path.parent,data.measurement_file,data.measurement_sha256)
        ns={'w':'http://www.opengis.net/wmts/1.0','o':'http://www.opengis.net/ows/1.1'}
        layer=next((e for e in xml.findall('.//w:Layer',ns) if e.findtext('o:Identifier',namespaces=ns)==data.wmts_layer),None)
        matrix=next((e for e in xml.findall('.//w:Contents/w:TileMatrixSet',ns) if e.findtext('o:Identifier',namespaces=ns)==data.wmts_matrix_set),None)
        if layer is None or matrix is None or matrix.findtext('o:SupportedCRS',namespaces=ns)!=NASA_CRS:
            raise ValueError('Capability identity mismatch')
        if data.wmts_matrix_set not in [e.text for e in layer.findall('w:TileMatrixSetLink/w:TileMatrixSet',ns)]:
            raise ValueError('Wrong matrix binding')
        from affine import Affine
        native=Affine(*grid.inventory['source_transform']);height,width=grid.inventory['source_shape']
        dx,dy=grid.metadata.source_resolution
        max_tolerance=min(50.0,2*min(dx,dy))
        residuals=[];positions=[]
        for obs in data.observations:
            col,row=obs.dem_pixel
            if not (1<=col<width-1 and 1<=row<height-1): raise ValueError('Control outside source')
            if not -180<=obs.wmts_coordinate[0]<=180 or not -90<=obs.wmts_coordinate[1]<=90: raise ValueError('Invalid angular observation')
            expected=grid.xy(obs.wire);positions.append(expected)
            dem_error=math.dist(expected,transform_point(native,(col,row)))
            mapped=MarsCoordinate(longitude=obs.wmts_coordinate[0]%360,latitude=planetocentric(obs.wmts_coordinate[1]))
            wmts_error=math.dist(expected,grid.xy(mapped))
            dem_tol=math.hypot(dx/2,dy/2,obs.wire_uncertainty_m,obs.feature_uncertainty_m)
            tile=next((e for e in matrix.findall('w:TileMatrix',ns) if e.findtext('o:Identifier',namespaces=ns)==obs.wmts_matrix_id),None)
            if tile is None: raise ValueError('Control matrix is unavailable')
            tw=float(tile.findtext('w:TileWidth',namespaces=ns));th=float(tile.findtext('w:TileHeight',namespaces=ns))
            mw=float(tile.findtext('w:MatrixWidth',namespaces=ns));mh=float(tile.findtext('w:MatrixHeight',namespaces=ns))
            top_left=[float(v) for v in tile.findtext('w:TopLeftCorner',namespaces=ns).split()]
            if top_left!=[-180,90] or not all(0<v<=1e8 and v.is_integer() for v in (tw,th,mw,mh)) or not math.isclose(tw*mw,2*th*mh):
                raise ValueError('Unsupported matrix geometry')
            angle=360/(tw*mw)
            lon,lat=obs.wmts_coordinate
            left=grid.xy(MarsCoordinate(longitude=(lon-angle/2)%360,latitude=mapped.latitude))
            right=grid.xy(MarsCoordinate(longitude=(lon+angle/2)%360,latitude=mapped.latitude))
            low=grid.xy(MarsCoordinate(longitude=lon%360,latitude=planetocentric(max(-90,lat-angle/2))))
            high=grid.xy(MarsCoordinate(longitude=lon%360,latitude=planetocentric(min(90,lat+angle/2))))
            actual_resolution=max(math.dist(left,right),math.dist(low,high),obs.wmts_resolution_m)
            map_tol=math.hypot(actual_resolution/math.sqrt(2),obs.wire_uncertainty_m,obs.feature_uncertainty_m)
            passed=dem_tol<=max_tolerance and map_tol<=max_tolerance and dem_error<=dem_tol and wmts_error<=map_tol
            residuals.append(ControlResidual(control_id=obs.control_id,dem_error_m=dem_error,wmts_error_m=wmts_error,
                dem_tolerance_m=dem_tol,wmts_tolerance_m=map_tol,passed=passed))
        polygon=hull(positions)
        area=abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2 if polygon else 0
        reasons=[]
        if len(polygon)<3 or area<16*dx*dy: reasons.append('Independent controls lack spatial spread or are collinear.')
        if not all(r.passed for r in residuals): reasons.append('Control residuals or uncertainty exceed the bounded registration tolerance.')
        if not all(covered(polygon,grid.xy(p)) for p in route): reasons.append('Route leaves the independently controlled footprint.')
        if not route: reasons.append('No route footprint was supplied for registration applicability.')
        result=result.model_copy(update=dict(map_alignment='verified' if not reasons else 'unverified',
            scope=[tuple(grid.inverse.transform(*p)) for p in polygon],residuals=residuals,reasons=reasons))
        return MapRegistration.model_validate(result.model_dump())
    except (OSError,ValueError,StopIteration,ET.ParseError):
        return result.model_copy(update={'map_alignment':'unverified','reasons':['Registration inputs are missing, incompatible, synthetic-only or failed source/capability integrity checks.']})


def control_snapshot(grid,report,*,dataset_root=None):
    if not report.controls_sha256 or not grid.profile.registration_controls: return None
    root=Path(dataset_root).resolve() if dataset_root else grid.source_path.parent
    path=(root/grid.profile.registration_controls).resolve()
    try:
        content=path.read_bytes() if path.is_relative_to(root) and path.stat().st_size<=1_000_000 else b''
        if hashlib.sha256(content).hexdigest()!=report.controls_sha256: raise ValueError('Changed control evidence')
        return content.decode('utf-8')
    except (OSError,ValueError):
        if report.map_alignment=='verified': raise ValueError('Verified control evidence changed before publication') from None
        return None


def registration_for_route(grid,route,*,dataset_root=None,allow_synthetic=False):
    name=grid.profile.registration_controls
    path=None
    if name:
        root=Path(dataset_root).resolve() if dataset_root else grid.source_path.parent
        candidate=(root/name).resolve()
        if Path(name).is_absolute() or not candidate.is_relative_to(root):
            return MapRegistration(source_sha256=grid.source_hash,reasons=['Registration controls must be inside the read-only dataset root.'])
        path=candidate
    return validate_controls(grid,path,route,allow_synthetic=allow_synthetic)
