import asyncio
from concurrent.futures import ThreadPoolExecutor
import heapq
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import rasterio
from affine import Affine
from fastapi.testclient import TestClient

from app.api.errors import ApiProblem
from app.contracts.api import COORDINATE_SYSTEM, PlanRouteRequest
from app.main import create_app
from app.planning.grid import load_grid, transform_point
from app.planning.search import astar
from app.planning.service import PlanningService
from app.planning.validation import validate_polyline

from pyproj import CRS as Projection

CRS = Projection.from_user_input('+proj=eqc +lat_ts=18.4663 +lon_0=0 +R=3396190 +units=m +no_defs +type=crs').to_wkt().replace('"unknown"', '"Mars_Synthetic"')


def fixture_profile(tmp_path, z=None, transform=None, crs=CRS, scale=1, offset=0, **updates):
    dem = tmp_path/'synthetic.tif'
    z = np.zeros((14,16),dtype='float32') if z is None else z.astype('float32')
    t = transform or Affine(20,0,4354000,0,-30,1094000)
    with rasterio.open(dem,'w',driver='GTiff',height=z.shape[0],width=z.shape[1],count=1,dtype='float32',
        crs=crs,transform=t,nodata=-9999) as dst:
        dst.write(z,1)
        dst.scales = (scale,)
        dst.offsets = (offset,)
    profile = dict(dem=dem.name,dataset_id='synthetic-plane',roi_id='synthetic-roi',window=[1,1,z.shape[1]-2,z.shape[0]-2],
        vertical_units='m',vertical_units_evidence='Synthetic generated metric plane fixture',**updates)
    path = tmp_path/'profile.json'
    path.write_text(json.dumps(profile))
    return path


def request_for(grid, a=(2,2), b=(8,10), mode='shortest'):
    return PlanRouteRequest(region_id='jezero',coordinate_system=COORDINATE_SYSTEM,
        start=grid.wire(*grid.center(a)),goal=grid.wire(*grid.center(b)),mode=mode)


def test_flat_incline_rectangular_scaling_halo_and_holes(tmp_path):
    y,x = np.mgrid[:14,:16]
    g = load_grid(fixture_profile(tmp_path,x*2+y*3,scale=2,offset=100))
    assert np.allclose(g.slope, math.degrees(math.atan(math.sqrt(.2**2+.2**2)))), 'Physical 20x30 spacing and vertical scale'
    assert not g.unknown.any() and g.coverage.all(), 'Halo supports all planning edges'
    assert g.blocked.all(), 'Known incline exceeds the demo threshold'
    z = np.zeros((14,16)); z[5,5] = -9999; z[8,8] = np.nan
    g = load_grid(fixture_profile(tmp_path,z))
    assert not g.coverage[4,4] and g.unknown[4,5] and not g.allowed[4,5]
    assert not g.coverage[7,7] and g.unknown[6,7]


@pytest.mark.parametrize('kind',['skew','earth','geographic','bad_units','limit','outside'])
def test_ingestion_rejections(tmp_path,kind):
    kwargs = {}
    if kind=='skew': kwargs['transform']=Affine(20,1,4354000,0,-30,1094000)
    if kind=='earth': kwargs['crs']='EPSG:32643'
    if kind=='geographic': kwargs['crs']='+proj=longlat +R=3396190 +type=crs'
    path = fixture_profile(tmp_path,**kwargs)
    p=json.loads(path.read_text())
    if kind=='bad_units': p['vertical_units']='feet'
    if kind=='limit': p['limits']={'max_grid_cells':5,'max_expanded_nodes':100,'max_elapsed_seconds':1}
    if kind=='outside': p['window']=[0,0,10,10]
    path.write_text(json.dumps(p))
    with pytest.raises((ValueError,ApiProblem)): load_grid(path)


def dijkstra(allowed, penalty, start, goal, dx, dy):
    # Independent adjacency construction and heap shortest path; no planner helpers.
    vertices=list(zip(*np.nonzero(allowed)))
    edges={v:[] for v in vertices}
    for a in vertices:
        for b in vertices:
            dr,dc=abs(a[0]-b[0]),abs(a[1]-b[1])
            if max(dr,dc)!=1: continue
            if dr and dc and (not allowed[a[0],b[1]] or not allowed[b[0],a[1]]): continue
            edges[a].append((b,math.hypot(dr*dy,dc*dx)*(penalty[a]+penalty[b])/2))
    q=[(0,start)]; visited=set()
    while q:
        cost,v=heapq.heappop(q)
        if v in visited: continue
        visited.add(v)
        if v==goal: return cost
        for b,w in edges[v]: heapq.heappush(q,(cost+w,b))
    return None


@pytest.mark.parametrize('seed',range(12))
def test_astar_matches_independent_dijkstra(seed):
    rng=np.random.default_rng(seed)
    allowed=rng.random((6,7))>.25; allowed[0,0]=allowed[-1,-1]=True
    for penalty in [np.ones(allowed.shape),1+rng.random(allowed.shape)*5]:
        expected=dijkstra(allowed,penalty,(0,0),(5,6),20,30)
        if expected is None:
            with pytest.raises(ApiProblem,match='No connected'): astar(allowed,penalty,(0,0),(5,6),20,30)
        else:
            result=astar(allowed,penalty,(0,0),(5,6),20,30)
            assert result.cost==pytest.approx(expected)
            assert result.cells==astar(allowed,penalty,(0,0),(5,6),20,30).cells


def test_corner_detour_policy_and_limits():
    allowed=np.ones((5,7),bool); allowed[2,3]=False
    penalty=np.ones(allowed.shape); penalty[1:4,2:5]=20
    short=astar(allowed,np.ones_like(penalty),(2,0),(2,6),1,1)
    safe=astar(allowed,penalty,(2,0),(2,6),1,1)
    assert short.cells != safe.cells
    assert all(allowed[x] for x in safe.cells)
    with pytest.raises(ApiProblem,match='limit'): astar(allowed,penalty,(2,0),(2,6),1,1,max_nodes=1)
    with pytest.raises(ApiProblem,match='limit'): astar(allowed,penalty,(2,0),(2,6),1,1,max_seconds=1e-12)
    corner=np.array([[1,0],[0,1]],bool)
    with pytest.raises(ApiProblem,match='No connected'): astar(corner,np.ones((2,2)),(0,0),(1,1),1,1)
    with pytest.raises(ValueError): astar(allowed,-penalty,(2,0),(2,6),1,1)


def test_geometry_and_independent_validation(tmp_path):
    g=load_grid(fixture_profile(tmp_path))
    req=request_for(g)
    for cell in [(0,0),(3,7),(11,13)]:
        assert g.cell(g.wire(*g.center(cell)))==cell
    # Independent analytic sphere projection fixture; wrong radius/axis can round-trip but fails this.
    point=req.start
    radius=3396190
    expected=(radius*math.radians(point.longitude)*math.cos(math.radians(18.4663)),radius*math.radians(point.latitude))
    assert g.xy(point)==pytest.approx(expected,abs=1e-7)
    x,y=g.center((3,3)); g.blocked[3,4]=True
    with pytest.raises(ApiProblem): validate_polyline(g,[(x,y),g.center((4,4))],g.source_hash)
    # Connector lies along a blocked neighbor boundary, despite its containing cell being valid.
    a=transform_point(g.transform,(4,3.25)); b=transform_point(g.transform,(4,3.75))
    with pytest.raises(ApiProblem): validate_polyline(g,[a,b],g.source_hash)
    with pytest.raises(ValueError): validate_polyline(g,[(-1,-1),g.center((0,0))],g.source_hash)
    with pytest.raises(ValueError): validate_polyline(g,[g.center((0,0)),g.center((9,9))],g.source_hash)
    with pytest.raises(ValueError): validate_polyline(g,[g.center((0,0)),g.center((0,1))],'changed')


def test_real_pipeline_api_restart_corruption_and_missing(tmp_path):
    profile=fixture_profile(tmp_path)
    service=PlanningService('computed',profile,tmp_path/'routes')
    assert service.ready, repr(service.failure)
    req=request_for(service.grid)
    with TestClient(create_app(planning=service)) as client:
        for mode in ['shortest','safest']:
            request=req.model_copy(update={'mode':mode})
            post=client.post('/api/v1/routes/plan',json=request.model_dump())
            assert post.status_code==200,post.text
            result=post.json(); rid=result['route_id']
            assert result['source']=='computed' and result['metrics']['distance_m']>0
            assert result['metrics']['risk_score'] is None
            stored=client.get('/api/v1/routes/'+rid).json()
            assert stored['result']==result
            assert all(w['status']=='unassessed' for w in stored['metadata']['workers'][1:])
            assert str(tmp_path) not in json.dumps(stored)
            with TestClient(create_app(planning=PlanningService('computed',None,tmp_path/'routes'))) as restarted:
                assert restarted.get('/api/v1/routes/'+rid).json()==stored
        assert client.get('/api/v1/routes/route-'+'0'*32).status_code==404
        assert client.get('/api/v1/routes/bad-id').status_code==422
        assert client.get('/api/v1/routes/..%2F..%2Fetc').status_code!=200
        folder=tmp_path/'routes'/rid
        (folder/'grid.npz').write_bytes(b'tampered')
        assert client.get('/api/v1/routes/'+rid).json()['error']['code']=='ROUTE_RECORD_INVALID'
        (folder/'complete.json').unlink()
        assert client.get('/api/v1/routes/'+rid).status_code==404


def test_region_advertises_loaded_window_not_full_raster(tmp_path):
    service = PlanningService('computed', fixture_profile(tmp_path), tmp_path/'routes')
    with TestClient(create_app(planning=service)) as client:
        region = client.get('/api/v1/regions').json()['regions'][0]
        assert region['routing_available'] is True
        assert region['planning']['bounds'] == service.grid.bounds.model_dump()
        assert region['planning']['resolution_m'] == [20.0, 30.0]
        assert region['planning']['example_request'] is None  # no CTX demo assumed for another ROI
    unavailable = PlanningService('computed', None, tmp_path/'unavailable')
    assert unavailable.describe_region().planning is None


def test_errors_same_cell_changed_source_and_storage(tmp_path,monkeypatch):
    service=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    g=service.grid
    req=request_for(g)
    with TestClient(create_app(planning=service)) as c:
        a=g.wire(*(transform_point(g.transform,(2.2,2.2)))); b=g.wire(*(transform_point(g.transform,(2.8,2.8))))
        same=req.model_copy(update={'start':a,'goal':b})
        result=c.post('/api/v1/routes/plan',json=same.model_dump())
        assert result.status_code==200,result.text
        assert len(result.json()['route'])==2
        assert result.json()['metrics']['distance_m']==pytest.approx(math.hypot(12,18))
        outside=PlanRouteRequest.model_validate({**req.model_dump(),'start':{'longitude':0.0,'latitude':0.0}})
        assert c.post('/api/v1/routes/plan',json=outside.model_dump()).json()['error']['code']=='OUTSIDE_PLANNING_COVERAGE'
        g.blocked[g.cell(req.start)]=True
        assert c.post('/api/v1/routes/plan',json=req.model_dump()).json()['error']['code']=='ENDPOINT_NOT_TRAVERSABLE'
        g.blocked[:]=False; g.blocked[:,6]=True
        assert c.post('/api/v1/routes/plan',json=req.model_dump()).json()['error']['code']=='NO_PATH'
        g.blocked[:]=False
        monkeypatch.setattr('app.planning.store.os.rename',lambda *args: (_ for _ in ()).throw(OSError('private path')))
        err=c.post('/api/v1/routes/plan',json=req.model_dump())
        assert err.status_code==500 and err.json()['error']['code']=='ROUTE_STORAGE_ERROR'
        assert not list((tmp_path/'routes').glob('.staging-*'))
        g.source_path.touch()
        assert c.post('/api/v1/routes/plan',json=req.model_dump()).json()['error']['code']=='PLANNING_UNAVAILABLE'
        assert c.get('/api/v1/regions').json()['regions'][0]['routing_available'] is False
    with TestClient(create_app(planning=PlanningService('computed',None,tmp_path/'empty'))) as c:
        assert c.post('/api/v1/routes/plan',json=req.model_dump()).json()['error']['code']=='PLANNING_UNAVAILABLE'
        assert not c.get('/api/v1/regions').json()['regions'][0]['routing_available']


def test_concurrent_storage_isolation(tmp_path):
    s=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    req=request_for(s.grid)
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda _:s.plan(req),range(4)))
    assert len({r.route_id for r in results})==4
    for r in results:
        assert s.store.get(r.route_id).result==r


def test_health_not_blocked_by_planning(tmp_path,monkeypatch):
    import httpx
    import threading
    s=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    entered=threading.Event(); release=threading.Event()
    original=s.plan
    def delayed(req):
        entered.set()
        assert release.wait(3)
        return original(req)
    monkeypatch.setattr(s,'plan',delayed)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(planning=s)),base_url='http://test') as c:
            task=asyncio.create_task(c.post('/api/v1/routes/plan',json=request_for(s.grid).model_dump()))
            while not entered.is_set(): await asyncio.sleep(.001)
            try:
                assert (await asyncio.wait_for(c.get('/api/v1/health'),.5)).status_code==200
            finally: release.set()
            assert (await task).status_code==200
    asyncio.run(run())


def test_no_optional_graph_imports():
    script='''
import sys
class Reject:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'langgraph','langchain_core','langsmith','openai'}:
            raise ImportError('Optional dependency blocked')
sys.meta_path.insert(0,Reject())
from app.main import create_app
from app.planning.service import PlanningService
assert create_app(planning=PlanningService()).state.planning.ready
'''
    subprocess.run([sys.executable,'-c',script],check=True)


def test_optional_inventory_defects_do_not_block_terrain(tmp_path):
    from app.planning.verify import inventory
    profile = fixture_profile(tmp_path)
    (tmp_path/'optional.tif').write_bytes(b'incomplete optional download')
    (tmp_path/'optional.tif.source.json').write_text('{broken receipt')
    result = inventory(tmp_path)
    assert any(x.get('unavailable') for x in result['rasters'])
    assert any(not x['verified'] for x in result['optional_receipts'])
    assert PlanningService('computed', profile, tmp_path/'routes').ready


def test_generated_browser_contract_and_fixture_match_server(tmp_path):
    from app.planning.export_contract import export
    from app.contracts.routes import StoredRouteResponse
    export(tmp_path)
    browser = Path(__file__).resolve().parents[2]/'frontend'
    for name in ['routeMetadata.ts', 'storedRoute.schema.json', 'chat.schema.json']:
        assert (tmp_path/name).read_bytes() == (browser/'src/types'/name).read_bytes()
    record = StoredRouteResponse.model_validate_json((browser/'tests/fixtures/computed-route.json').read_text())
    assert record.metadata.sources[0].dataset_id == 'synthetic-plane'


def test_missing_optional_raster_dependencies_return_unavailable():
    script = '''
import sys
class Reject:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'numpy', 'rasterio', 'pyproj'}:
            raise ImportError('Optional raster dependency blocked')
sys.meta_path.insert(0, Reject())
from fastapi.testclient import TestClient
from app.main import create_app
from app.planning.service import PlanningService
from app.contracts.api import COORDINATE_SYSTEM
with TestClient(create_app(planning=PlanningService('computed'))) as client:
    response = client.post('/api/v1/routes/plan', json={
        'region_id':'jezero', 'coordinate_system':COORDINATE_SYSTEM, 'mode':'shortest',
        'start':{'longitude':77.4,'latitude':18.4}, 'goal':{'longitude':77.5,'latitude':18.5}})
    assert response.status_code == 503, response.text
    assert response.json()['error']['code'] == 'PLANNING_UNAVAILABLE'
'''
    subprocess.run([sys.executable, '-c', script], check=True)
