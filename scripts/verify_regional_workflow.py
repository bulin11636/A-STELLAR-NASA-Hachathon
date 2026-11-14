#!/usr/bin/env python3
"""Real DEM/API acceptance for regional routing and multi-stop chat; model is mocked."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=ROOT/'data/samples/a0-planning-profile.example.json')
    parser.add_argument('--output-root',type=Path,default=ROOT/'data/processed/regional-verification')
    args = parser.parse_args()
    os.environ['A_STELLAR_A0_MODE'] = 'deterministic'
    import httpx
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.planning.grid import digest
    from app.planning.service import PlanningService
    from app.contracts.api import MarsCoordinate
    from app.coordinator.settings import AgentSettings
    from app.coordinator.route_agent import RouteAgent
    from app.coordinator.metered import MeteredProvider
    run = args.output_root.resolve()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(parents=True)
    summary = {'status':'running','model':'mocked','live_model_calls':0,'run_path':str(run)}
    def save(name,body):
        (run/name).write_text(json.dumps(body,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
    try:
        planning = PlanningService('computed',args.profile,run/'routes',dataset_root=args.dataset_dir)
        if not planning.ready:
            raise RuntimeError('The configured DEM/profile is unavailable.')
        before = digest(planning.grid.source_path)
        regional = planning.regional_example()
        if regional is None:
            raise RuntimeError('This profile cannot advertise the Jezero regional demonstration.')
        g = planning.grid
        stops = [g.wire(*g.center(cell)) for cell in [(20,20),(30,30),(40,40),(50,50),(60,60),(70,70),(80,80),(90,90)]]
        if any(not g.allowed[g.cell(p)] for p in stops):
            raise RuntimeError('The selected real-DEM stop fixture includes a blocked cell.')
        settings = AgentSettings(enabled=True,api_key='synthetic-verification-key')
        def handler(req):
            message = json.loads(json.loads(req.content)['input'][1]['content'])['message']
            ordered = list(reversed(stops)) if message.startswith('Reverse') else stops
            answer = message.startswith('Why')
            proposal = dict(action='answer' if answer else 'replan',message='Mock proposal; inspect host-validated terrain facts.',
                mode=None,waypoints=[p.model_dump() for p in ordered] if message.startswith(('Add','Reverse')) else None,citations=['A1'])
            return httpx.Response(200,json=dict(status='completed',output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
                usage=dict(input_tokens=500,output_tokens=100)))
        provider = MeteredProvider(settings,run/'mock-usage',httpx.MockTransport(handler))
        agent = RouteAgent(settings,planning,provider)
        with TestClient(create_app(planning=planning,route_agent=agent,static_dir=ROOT/'frontend/dist')) as client:
            def post(path,body):
                response = client.post(path,json=body)
                if response.status_code != 200:
                    raise RuntimeError(f'Acceptance request failed: {response.status_code} '+response.json()['error']['code'])
                return response.json()
            assert client.get('/').status_code == 200
            assert client.get('/api/v1/ready').status_code == 200
            initial = post('/api/v1/routes/plan',regional.model_dump(mode='json'))
            route_id = initial['route_id']
            stored = client.get('/api/v1/routes/'+route_id).json()
            save('regional-route.json',stored)
            assert initial['metrics']['distance_m'] > 40_000, 'Expected a crater-scale distance.'
            assert stored['metadata']['grid']['planning_resolution_m'][0] > stored['metadata']['grid']['source_resolution'][0], 'The regional fixture must exercise adaptive aggregation.'
            validation = json.loads((planning.store.root/route_id/'validation.json').read_text())
            assert validation['native_validation']['status'] == 'passed'
            save('regional-native-validation.json',validation['native_validation'])
            # The opposite direction exercises another endpoint order across the crater.
            reverse_request = regional.model_copy(update={'start':regional.goal,'goal':regional.start})
            reverse = post('/api/v1/routes/plan',reverse_request.model_dump(mode='json'))
            save('opposite-direction.json',client.get('/api/v1/routes/'+reverse['route_id']).json())
            def demo_position(longitude,latitude):
                full = planning._regional_grid
                target = MarsCoordinate(longitude=longitude,latitude=latitude)
                r,c = full.cell(target)
                allowed = full.allowed
                candidates = [(rr,cc) for rr in range(max(0,r-5),min(allowed.shape[0],r+6))
                    for cc in range(max(0,c-5),min(allowed.shape[1],c+6)) if allowed[rr,cc]]
                if not candidates: raise RuntimeError('No conservative demonstration point near the regional target.')
                chosen = min(candidates,key=lambda cell:(cell[0]-r)**2+(cell[1]-c)**2)
                return full.wire(*full.center(chosen))
            cases = {
                'other-diagonal': regional.model_copy(update={'start':demo_position(77.1,18.75),'goal':demo_position(77.9,18.15)}),
                'north-south': regional.model_copy(update={'start':demo_position(77.5,18.0),'goal':demo_position(77.5,18.9)}),
                'terrain-weighted': regional.model_copy(update={'mode':'safest'}),
            }
            regional_cases = {}
            for name,case in cases.items():
                planned = post('/api/v1/routes/plan',case.model_dump(mode='json'))
                record = client.get('/api/v1/routes/'+planned['route_id']).json()
                save(name+'.json',record)
                regional_cases[name] = dict(distance_m=planned['metrics']['distance_m'],mode=planned['mode'],
                    search_resolution_m=record['metadata']['grid']['planning_resolution_m'])
            message = 'Add these eight required points, in this exact order, retaining start and goal: '+ '; '.join(f'{p.longitude},{p.latitude}' for p in stops)
            added = post('/api/v1/routes/'+route_id+'/chat',dict(message=message,request_id=uuid4().hex))
            assert added['metadata']['request']['waypoints'] == [p.model_dump() for p in stops]
            child = added['result']['route_id']; save('added-eight-stops.json',added)
            reordered = post('/api/v1/routes/'+child+'/chat',dict(message='Reverse all eight waypoint visits; retain the start, goal and shortest objective.',request_id=uuid4().hex))
            assert reordered['metadata']['request']['waypoints'] == [p.model_dump() for p in reversed(stops)]
            final = reordered['result']['route_id']; save('reordered-eight-stops.json',reordered)
            answer = post('/api/v1/routes/'+final+'/chat',dict(message='Why was this order selected?',request_id=uuid4().hex))
            assert answer['result'] is None
        # New service instances re-read disk; no in-memory route or chat cache.
        fresh = PlanningService('computed',args.profile,planning.store.root,dataset_root=args.dataset_dir)
        with TestClient(create_app(planning=fresh,route_agent=RouteAgent(settings,fresh,provider))) as client:
            assert len(client.get('/api/v1/routes/'+final+'/chat').json()['messages']) == 3
            assert client.get('/api/v1/routes/'+route_id).json()['result'] == initial
            assert client.get('/api/v1/routes/'+final).status_code == 200
        assert digest(planning.grid.source_path) == before
        summary.update(status='passed',source_sha256=before,distance_m=initial['metrics']['distance_m'],
            source_resolution_m=stored['metadata']['grid']['source_resolution'],search_resolution_m=stored['metadata']['grid']['planning_resolution_m'],
            search_shape=[stored['metadata']['grid']['height'],stored['metadata']['grid']['width']],
            initial_route_id=route_id,final_route_id=final,mock_provider_calls=provider.totals()['attempts'],
            regional_cases=regional_cases,
            checks=['production_ui_same_origin_api','regional_forward_and_reverse','other_diagonal_and_north_south','terrain_weighted_mode','independent_native_segment_checks',
                'chat_add_eight_points','chat_reverse_all_visits','answer_without_revision','fresh_service_history_and_immutable_routes','source_bytes_unchanged'])
    except Exception as error:
        summary.update(status='failed',error_type=type(error).__name__,message=str(error) if isinstance(error,(AssertionError,RuntimeError)) else 'Inspect the local offline checks.')
    save('summary.json',summary)
    print(json.dumps(summary,indent=2))
    return 0 if summary['status']=='passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
