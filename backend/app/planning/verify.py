"""Explicit local real-DEM acceptance. Never imported or skipped by default tests."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

from app.contracts.api import COORDINATE_SYSTEM, MarsCoordinate, PlanRouteRequest
from app.contracts.routes import StoredRouteResponse
from app.planning.grid import digest
from app.planning.service import PlanningService
from app.planning.validation import validate_polyline


def save(path,data):
    Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def inventory(root):
    import rasterio
    rasters=[]
    for path in sorted(root.glob('*.tif')):
        try:
            with rasterio.open(path) as s:
                rasters.append(dict(filename=path.name,bytes=path.stat().st_size,shape=s.shape,crs=s.crs.to_wkt() if s.crs else None,
                    affine=tuple(s.transform)[:6],nodata=str(s.nodata),resolution=s.res,scales=s.scales,offsets=s.offsets,band_units=s.units,tags=s.tags()))
        except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
            rasters.append(dict(filename=path.name,unavailable=str(exc)))
    receipts=[]
    for path in sorted(root.rglob('*.source.json')):
        source=path.with_name(path.name.removesuffix('.source.json'))
        try:
            record=json.loads(path.read_text())
            ok=source.is_file() and source.stat().st_size==record['bytes'] and digest(source)==record['sha256']
            receipts.append(dict(file=str(source.relative_to(root)),source_url=record['source_url'],sha256=record['sha256'],verified=ok))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            receipts.append(dict(file=str(source.relative_to(root)),verified=False,unavailable=str(exc)))
    # Receipt integrity never establishes specialist scientific readiness.
    from app.agents.a3.inspection import inspect_cached
    try:
        rad=inspect_cached(root/'a3-radiation/msl-rad-rdr')
        radiation=dict(observations=len(rad.observations),baseline_eligible=sum(x.baseline_eligible for x in rad.observations),warnings=rad.warnings)
    except (OSError,ValueError,KeyError) as e:
        radiation=dict(unavailable=str(e))
    snapshots=[]
    from app.evidence.snapshots import load_snapshots
    for path in sorted((root/'evidence').glob('*/manifest.json')):
        try:
            manifest, content=load_snapshots(path)
            snapshots.append(dict(file=str(path.relative_to(root)),verified=True,dataset_version=manifest.dataset_version,sources=list(content)))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            snapshots.append(dict(file=str(path.relative_to(root)),verified=False,unavailable=str(exc)))
    image_manifests=list((root/'a6-observations').glob('**/manifest.json'))
    return dict(rasters=rasters,optional_receipts=receipts,rad_inspection=radiation,evidence_snapshots=snapshots,
        a6_image_manifests=[str(p.relative_to(root)) for p in image_manifests],
        optional_status='A2/A3/A4/A6 unassessed for routing; receipt integrity does not supply aligned mission constraints. '+
            ('A6 image manifests require separate product validation.' if image_manifests else 'No A6 image manifests found.'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--dataset-dir',required=True,type=Path)
    parser.add_argument('--output-root',required=True,type=Path)
    args=parser.parse_args()
    os.environ['A_STELLAR_DATASET_DIR']=str(args.dataset_dir.resolve())
    run=args.output_root.resolve()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(parents=True)
    command=[sys.executable,'-m','app.planning.verify',*sys.argv[1:]]
    summary=dict(command=command,run_path=str(run),status='running',checks={},routes=[],
        versions={x:importlib.metadata.version(x) for x in ['numpy','rasterio','pyproj','fastapi','pydantic','httpx','uvicorn','pytest']},
        python=sys.version,blockers=['NASA WMTS/wire/DEM registration and browser computed overlay remain unverified.'])
    server=None
    try:
        save(run/'input-inventory.json',inventory(args.dataset_dir.resolve()))
        profile=json.loads(args.profile.read_text())
        # Resolve source into an explicit private run profile, independent of CWD.
        profile['dem']=str((args.dataset_dir.resolve()/profile['dem']).resolve())
        save(run/'profile.json',profile)
        service=PlanningService('computed',run/'profile.json',run/'routes')
        if not service.ready:
            raise RuntimeError(f'Planning unavailable: {service.failure!r}')
        g=service.grid
        save(run/'grid-inventory.json',dict(**g.inventory,grid=g.metadata.model_dump(mode='json'),bounds=g.bounds.model_dump(),
            source_sha256=g.source_hash,valid_cells=int(g.allowed.sum())))
        # Explicit known demo endpoints, selected on valid cells. Do not use mock coordinates.
        start_cell=(20,20); goal_cell=(100,100)
        if g.metadata.height<=100 or g.metadata.width<=100 or not g.allowed[start_cell] or not g.allowed[goal_cell]:
            raise RuntimeError('Profile must contain the documented 128x128 demonstration endpoint cells')
        request=PlanRouteRequest(region_id='jezero',coordinate_system=COORDINATE_SYSTEM,
            start=g.wire(*g.center(start_cell)),goal=g.wire(*g.center(goal_cell)),mode='shortest')
        # Independent PDS source control, not merely an inverse transform round trip.
        fixture=Path(__file__).resolve().parents[3]/'data/fixtures/jezero-pds-control.json'
        control=json.loads(fixture.read_text())
        projected=g.xy(MarsCoordinate.model_validate(control['wire_coordinate']))
        delta=math.dist(projected,(control['source_projected']['easting_m'],control['source_projected']['northing_m']))
        if delta>0.02:
            raise RuntimeError('DEM source projection disagrees with the recorded PDS control')
        summary['checks']['pds_source_projection_control']=dict(passed=True,error_m=delta,tolerance_m=.02,
            scope='Independent projected/wire registration only; not WMTS feature alignment')
        import httpx
        from fastapi.testclient import TestClient
        from app.main import create_app
        # Reserve a local port, then launch the actual ASGI application in a new process.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        env={**os.environ,'A_STELLAR_A0_MODE':'deterministic','A_STELLAR_ROUTING_MODE':'computed','A_STELLAR_PLANNING_PROFILE':str(run/'profile.json'),
            'A_STELLAR_ROUTE_STORE':str(run/'routes')}
        log=(run/'server.log').open('w')
        def launch():
            process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    if process.poll() is not None: raise RuntimeError('Server exited; inspect server.log')
                    try:
                        if httpx.get(base+'/api/v1/health',timeout=.3).status_code==200: return process
                    except httpx.HTTPError: pass
                    time.sleep(.05)
                raise RuntimeError('Server startup timed out')
            except BaseException:
                process.terminate(); process.wait(timeout=10); raise
        server=launch()
        summary['server_command']=[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)]
        with httpx.Client(base_url=base,timeout=20) as client:
            assert client.get('/api/v1/regions').json()['regions'][0]['routing_available']
            for mode in ['shortest','safest']:
                req=request.model_copy(update={'mode':mode})
                save(run/f'request-{mode}.json',req.model_dump(mode='json'))
                post=client.post('/api/v1/routes/plan',json=req.model_dump(mode='json'))
                save(run/f'response-{mode}.json',post.json())
                assert post.status_code==200,post.text
                result=post.json()
                response=client.get('/api/v1/routes/'+result['route_id'])
                assert response.status_code==200,response.text
                stored=StoredRouteResponse.model_validate(response.json())
                assert stored.result.model_dump(mode='json')==result
                assert stored.result.source=='computed' and stored.result.route[0]==req.start and stored.result.route[-1]==req.goal
                distance,cells=validate_polyline(g,[g.xy(p) for p in stored.result.route],g.source_hash)
                assert abs(distance-stored.result.metrics.distance_m)<1e-5
                # Independently sample every emitted segment at <=1/8 cell spacing.
                for a,b in zip(stored.result.route,stored.result.route[1:]):
                    p,q=g.xy(a),g.xy(b)
                    count=max(1,math.ceil(math.dist(p,q)/(min(g.metadata.planning_resolution_m)/8)))
                    for i in range(count+1):
                        xy=(p[0]+(q[0]-p[0])*i/count,p[1]+(q[1]-p[1])*i/count)
                        assert g.allowed[g.cell(g.wire(*xy))]
                save(run/f'stored-{mode}.json',stored.model_dump(mode='json'))
                summary['routes'].append(dict(mode=mode,route_id=result['route_id'],distance_m=distance,
                    objective_cost=stored.metadata.planner.objective_cost,expanded_nodes=stored.metadata.planner.expanded_nodes,
                    elapsed_ms=stored.metadata.planner.elapsed_ms,artifact_path=str(run/'routes'/result['route_id']),
                    touched_cells=len(cells)))
            invalid=request.model_copy(update={'start':MarsCoordinate(longitude=0.0,latitude=0.0)})
            response=client.post('/api/v1/routes/plan',json=invalid.model_dump(mode='json'))
            assert response.status_code==400 and response.json()['error']['code']=='OUTSIDE_PLANNING_COVERAGE'
            save(run/'negative-outside-coverage.json',response.json())
        # Stop the process completely, start a new interpreter/application, retrieve the same records.
        old_pid=server.pid
        server.terminate(); server.wait(timeout=10); server=launch()
        for entry in summary['routes']:
            response=httpx.get(base+'/api/v1/routes/'+entry['route_id'],timeout=20)
            expected=json.loads((run/f"stored-{entry['mode']}.json").read_text())
            assert response.status_code==200 and response.json()==expected
            save(run/f"restarted-{entry['mode']}.json",response.json())
        summary['checks']['http_process_restart_retrieval']=dict(passed=True,old_pid=old_pid,new_pid=server.pid)
        # Real terrain with explicitly injected masks, through API, kept separate from persisted natural-grid successes.
        with TestClient(create_app(planning=service)) as client:
            g.blocked[start_cell]=True
            response=client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'))
            assert response.status_code==400 and response.json()['error']['code']=='ENDPOINT_NOT_TRAVERSABLE'
            save(run/'injected-blocked-endpoint.json',response.json())
            g.blocked[start_cell]=False; g.blocked[:,60]=True
            response=client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'))
            assert response.status_code==422 and response.json()['error']['code']=='NO_PATH'
            save(run/'injected-disconnected-mask.json',response.json())
        summary['checks'].update(real_dem_both_objectives=True,all_emitted_segments_valid=True,
            outside_coverage_rejected=True,injected_blocked_endpoint_rejected=True,injected_disconnected_mask_no_path=True,
            unsupported_metrics_null=all(json.loads((run/f"response-{m}.json").read_text())['metrics'][k] is None
                for m in ['shortest','safest'] for k in ['risk_score','estimated_time_min']),map_alignment='unverified',browser_display='pending')
        summary['status']='passed_backend_acceptance_frontend_alignment_pending'
    except BaseException as exc:
        summary['status']='failed'; summary['failure']=repr(exc)
        raise
    finally:
        if server is not None:
            server.terminate(); server.wait(timeout=10)
        save(run/'summary.json',summary)
        (run/'report.md').write_text('# Explicit real DEM acceptance\n\nCommand:\n\n```text\n'+' '.join(command)+'\n```\n\n'+
            'Status: '+summary['status']+'\n\n'+json.dumps(summary,indent=2)+'\n\n'+
            'Natural-grid successes use the original DEM. Negative mask cases are injected, labeled and never published as natural observations.\n'+
            'No live model, automatic download, deployment or computed browser overlay was performed.\n')
        print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
