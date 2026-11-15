#!/usr/bin/env python3
"""Real Jezero DEM P1 profile/resolution API acceptance; deterministic, zero model calls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=ROOT/'data/samples/a0-planning-profile.example.json')
    parser.add_argument('--output-root',type=Path,default=ROOT/'data/processed/p1-verification')
    args=parser.parse_args();os.environ['A_STELLAR_A0_MODE']='deterministic'
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.contracts.api import PlanRouteRequest, COORDINATE_SYSTEM
    from app.contracts.assessment import WalkingMission
    from app.planning.grid import digest,regional_grid
    from app.planning.service import PlanningService
    from app.planning.policies import configure_grid
    run=args.output_root.resolve()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);run.mkdir(parents=True)
    summary=dict(status='running',live_model_calls=0,run_path=str(run),cases={})
    def save(name,value): (run/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    try:
        planning=PlanningService('computed',args.profile,run/'routes',dataset_root=args.dataset_dir)
        if not planning.ready: raise RuntimeError('The configured real DEM/profile is unavailable.')
        source_before=digest(planning.grid.source_path)
        example=planning.regional_example()
        if example is None: raise RuntimeError('A crater-scale example is unavailable.')
        grids=[]
        for resolution in ('coarse','standard','fine'):
            request=example.model_copy(update={'mode':'safest','mission_profile':'balanced','resolution_profile':resolution})
            grids.append(regional_grid(args.profile,configure_grid(planning.grid,request),args.dataset_dir))
        # Choose shared feasible endpoints rather than hiding conservative aggregation exclusions.
        endpoints=[]
        coarse=grids[0]
        for target in (example.start,example.goal):
            r,c=coarse.cell(target);candidates=[]
            for rr in range(max(0,r-12),min(coarse.allowed.shape[0],r+13)):
                for cc in range(max(0,c-12),min(coarse.allowed.shape[1],c+13)):
                    if not coarse.allowed[rr,cc]: continue
                    point=coarse.wire(*coarse.center((rr,cc)))
                    if all(g.allowed[g.cell(point)] for g in grids): candidates.append(point)
            if not candidates: raise RuntimeError('No common conservative endpoint near this regional target.')
            endpoints.append(min(candidates,key=lambda p:(p.longitude-target.longitude)**2+(p.latitude-target.latitude)**2))
        del grids
        base=PlanRouteRequest(region_id='jezero',coordinate_system=COORDINATE_SYSTEM,start=endpoints[0],goal=endpoints[1],
            mode='safest',mission_profile='balanced',mission=WalkingMission(speed_m_s=1.0))
        with TestClient(create_app(planning=planning)) as client:
            assert client.get('/api/v1/planning/policies').status_code==200
            for profile in ('fastest','safest','science_priority','balanced'):
                for resolution in ('coarse','standard','fine'):
                    name=profile+'-'+resolution
                    request=base.model_copy(update={'mission_profile':profile,'resolution_profile':resolution,
                        'mode':'shortest' if profile=='fastest' else 'safest'})
                    key='p1-real-'+name+'-'+uuid4().hex[:8]
                    response=client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key})
                    if response.status_code!=200: raise RuntimeError(name+': '+response.json()['error']['code'])
                    result=response.json();record=client.get('/api/v1/routes/'+result['route_id']).json();a=record['metadata']['assessment']
                    assert a['hard_gate_status']=='unassessed' and a['risk_score'] is None
                    assert any(f['agent_id']=='A5' and f['status']=='not_applicable' for f in a['risk_factors'])
                    assert record['metadata']['registration']['map_alignment']=='unverified'
                    assert result['metrics']['estimated_time_min']==result['metrics']['distance_m']/60
                    assert record['metadata']['planning_policy']['actual_cell_size_m']==record['metadata']['grid']['planning_resolution_m']
                    validation=json.loads((planning.store.root/result['route_id']/'validation.json').read_text())
                    assert validation['native_validation']['status']=='passed'
                    assert client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key}).json()==result
                    save(name+'.json',record)
                    summary['cases'][name]=dict(route_id=result['route_id'],distance_m=result['metrics']['distance_m'],
                        resolution_m=record['metadata']['grid']['planning_resolution_m'],confidence=a['assessment_confidence'])
                    print('passed '+name,flush=True)
        fresh=PlanningService('computed',args.profile,planning.store.root,dataset_root=args.dataset_dir)
        with TestClient(create_app(planning=fresh)) as client:
            for case in summary['cases'].values(): assert client.get('/api/v1/routes/'+case['route_id']).status_code==200
        assert digest(planning.grid.source_path)==source_before
        summary.update(status='passed',source_sha256=source_before,checks=['four_versioned_profiles','three_bounded_resolutions',
            'actual_grid_costs_and_limits','real_crater_scale_routes','independent_native_validation','walking_estimate',
            'missing_required_radiation_blocks_comparison','explicit_A5_status','unverified_NASA_registration',
            'idempotent_replay','fresh_process_retrieval','source_bytes_unchanged'])
    except Exception as error:
        summary.update(status='failed',error_type=type(error).__name__,message=str(error) if isinstance(error,(RuntimeError,AssertionError)) else 'Inspect local offline acceptance.')
    save('summary.json',summary);print(json.dumps(summary,indent=2))
    return 0 if summary['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
