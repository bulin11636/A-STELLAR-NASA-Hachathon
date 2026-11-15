#!/usr/bin/env python3
"""Export P0 API fixtures from a synthetic DEM and a strictly mocked provider."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))


def export(destination):
    # Fixture construction cannot use the caller's live provider configuration.
    import httpx
    from fastapi.testclient import TestClient
    from app.contracts.api import COORDINATE_SYSTEM, PlanRouteRequest
    from app.contracts.chat import ChatRequest
    from app.coordinator.metered import MeteredProvider
    from app.coordinator.route_agent import RouteAgent
    from app.coordinator.settings import AgentSettings
    from app.main import create_app
    from app.planning.service import PlanningService
    from verify_docker import synthetic_inputs

    output = {}
    output['chat-request.schema.json'] = ChatRequest.model_json_schema(mode='validation')
    with TemporaryDirectory(prefix='stellar-p0-fixtures-') as temporary:
        folder = Path(temporary)
        datasets, profile = synthetic_inputs(folder)
        planning = PlanningService('computed', profile, folder/'routes', dataset_root=datasets)
        grid = planning.grid
        request = PlanRouteRequest(region_id='jezero', coordinate_system=COORDINATE_SYSTEM,
            start=grid.wire(*grid.center((20,20))), goal=grid.wire(*grid.center((100,100))), mode='shortest')
        parent = planning.plan(request)
        settings = AgentSettings(enabled=True, api_key='fixture-only', usage_root=folder/'usage')
        behavior = 'success'
        entered, release = Event(), Event()
        def handler(req):
            if behavior == 'timeout':
                raise httpx.ReadTimeout('synthetic timeout', request=req)
            if behavior == 'reject':
                return httpx.Response(429, json={'error':{'code':'rate_limit_exceeded'}})
            if behavior == 'running':
                entered.set()
                if not release.wait(10):
                    raise RuntimeError('Fixture worker was not released')
            message = json.loads(json.loads(req.content)['input'][1]['content'])['message']
            proposal = dict(action='replan', message='Propose the requested objective; the host computes the terrain route.',
                mode='safest' if message.startswith('Switch') else None, waypoints=None, citations=['A1'])
            return httpx.Response(200, json=dict(status='completed',
                output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
                usage=dict(input_tokens=500,output_tokens=100)))
        provider = MeteredProvider(settings, folder/'usage', httpx.MockTransport(handler))
        agent = RouteAgent(settings, planning, provider)
        with TestClient(create_app(planning=planning,route_agent=agent)) as client:
            def plan_status(name, status_code):
                key = 'fixture-'+name
                response = client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key})
                assert response.status_code == status_code, response.text
                output[name+'.json'] = client.get('/api/v1/routes/requests/'+key).json()
                return response
            behavior = 'running'
            key = 'fixture-plan-running'
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(client.post,'/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key})
                assert entered.wait(10)
                try:
                    output['plan-running.json'] = client.get('/api/v1/routes/requests/'+key).json()
                finally:
                    release.set()
                assert future.result(timeout=10).status_code == 200
            behavior = 'success'
            plan_status('plan-succeeded',200)
            behavior = 'reject'
            plan_status('plan-failed-retryable',503)
            behavior = 'timeout'
            plan_status('plan-unknown',503)
            invalid = {**request.model_dump(mode='json'),'start':{'longitude':0,'latitude':0}}
            key = 'fixture-plan-failed-non-retryable'
            assert client.post('/api/v1/routes/plan',json=invalid,headers={'Idempotency-Key':key}).status_code == 400
            output['plan-failed-non-retryable.json'] = client.get('/api/v1/routes/requests/'+key).json()
            chat_url = '/api/v1/routes/'+parent.route_id+'/chat'
            body = dict(message='Explain the terrain limits.',request_id='fixture-chat-failed-retryable')
            behavior = 'reject'
            assert client.post(chat_url,json=body).status_code == 503
            output['chat-failed-retryable.json'] = client.get(chat_url+'/attempts/'+body['request_id']).json()
            body = dict(message='Switch to safest mode while keeping the original stops.',request_id='fixture-chat-succeeded-revision',
                advanced_context=dict(schema_version='1',interface_mode='advanced',route_objective='shortest',required_waypoints=[],
                    analysis_focus=['terrain','operations'],allow_supported_revision=True))
            behavior = 'success'
            response = client.post(chat_url,json=body)
            assert response.status_code == 200, response.text
            assert response.json()['result'] is not None
            output['chat-succeeded-revision.json'] = response.json()
            output['chat-succeeded-revision.status.json'] = client.get(chat_url+'/attempts/'+body['request_id']).json()
            output['chat-succeeded-revision.request.json'] = body
            output['parent-route.json'] = client.get('/api/v1/routes/'+parent.route_id).json()
        # Only UUID-based route references and wall-clock fields are normalized.
        # Coordinate/route/artifact data remain actual synthetic-host outputs.
        child = output['chat-succeeded-revision.json']['result']['route_id']
        def stable(value):
            if isinstance(value,dict):
                return {key: '2026-11-15T00:00:00Z' if key in ('created_at','updated_at') and val is not None else stable(val)
                    for key,val in value.items()}
            if isinstance(value,list):
                return [stable(item) for item in value]
            if isinstance(value,str):
                return value.replace(parent.route_id,'route-'+'0'*32).replace(child,'route-'+'1'*32)
            return value
        destination.mkdir(parents=True,exist_ok=True)
        for name, value in output.items():
            (destination/name).write_text(json.dumps(stable(value),indent=2,allow_nan=False)+'\n')
    return sorted(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'data/fixtures/p0')
    args = parser.parse_args()
    os.environ['A_STELLAR_A0_MODE'] = 'deterministic'
    print(json.dumps(dict(files=export(args.output_dir),live_model_calls=0),indent=2))


if __name__ == '__main__':
    main()
