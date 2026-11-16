"""Local browser-test fixture: real DEM and host planner, explicitly mocked model."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from threading import Event, Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--port',type=int,required=True)
    args = parser.parse_args()
    os.environ['A_STELLAR_A0_MODE'] = 'deterministic'
    import httpx
    import uvicorn
    from app.main import create_app
    from app.api.frontend import mount_frontend
    from app.coordinator.settings import AgentSettings
    from app.coordinator.metered import MeteredProvider
    from app.coordinator.route_agent import RouteAgent
    from app.planning.service import PlanningService
    planning = PlanningService('computed',ROOT/'data/samples/a0-planning-profile.example.json',args.run_dir/'routes',dataset_root=args.dataset_dir)
    if not planning.ready:
        raise RuntimeError('Browser fixture needs the configured local CTX DEM.')
    control = {'next':'normal','target':'any','calls':0}
    control_lock = Lock()
    release = Event(); release.set()
    def handler(req):
        mission = json.loads(json.loads(req.content)['input'][1]['content'])
        message = mission['message']
        kind = 'plan' if message.startswith('Plan the supplied route') else 'chat'
        with control_lock:
            control['calls'] += 1
            behavior = control['next'] if control['target'] in ('any',kind) else 'normal'
            if behavior != 'normal': control['next'] = 'normal'
        if behavior == 'rate_limit_once':
            return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded'}})
        if behavior == 'timeout_once':
            raise httpx.ReadTimeout('Synthetic acceptance timeout',request=req)
        if behavior == 'hold_once' and not release.wait(30):
            raise httpx.ReadTimeout('Synthetic acceptance hold expired',request=req)
        from mock_specialists import selection_response
        selected=selection_response(json.loads(req.content))
        if selected is not None: return httpx.Response(200,json=selected)
        context = mission['mission'].get('advanced_context')
        before = context['required_waypoints'] if context else mission['mission']['request'].get('waypoints',[])
        waypoints = None
        if message.startswith('Add required points:'):
            waypoints = before + [dict(longitude=float(x),latitude=float(y)) for x,y in re.findall(r'(\d+\.\d+)\s*,\s*(\d+\.\d+)',message)]
        if message.startswith('Reverse all waypoint visits'):
            waypoints = list(reversed(before))
        proposal = dict(action='replan' if kind == 'plan' or message.startswith(('Add required points:', 'Reverse all waypoint visits', 'Use safest')) else 'answer',
            message='Mock A0 proposal: the host validates terrain routing and preserves exact required stop order.',
            mode='safest' if message.startswith('Use safest') else None,waypoints=waypoints,citations=['A1'])
        return httpx.Response(200,json=dict(status='completed',output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
            usage=dict(input_tokens=500,output_tokens=100)))
    settings = AgentSettings(enabled=True,api_key='synthetic-browser-key',usage_root=args.run_dir/'mock-usage',max_calls=200)
    provider = MeteredProvider(settings,args.run_dir/'mock-usage',httpx.MockTransport(handler))
    app = create_app(planning=planning,route_agent=RouteAgent(settings,planning,provider))
    @app.get('/__test/provider',include_in_schema=False)
    def provider_state():
        with control_lock: return dict(control)
    @app.post('/__test/budget',include_in_schema=False)
    def set_budget(body: dict[str,int]):
        settings.max_calls=body['max_calls']
        return provider.totals()
    @app.post('/__test/provider',include_in_schema=False)
    def configure_provider(body: dict[str,str]):
        behavior, target = body.get('next','normal'), body.get('target','any')
        if behavior not in ('normal','rate_limit_once','timeout_once','hold_once') or target not in ('any','plan','chat'):
            from app.api.errors import ApiProblem
            raise ApiProblem(422,'VALIDATION_ERROR','Unknown synthetic provider scenario.')
        if behavior == 'hold_once': release.clear()
        else: release.set()
        with control_lock: control.update(next=behavior,target=target)
        return dict(control)
    @app.get('/__test/scenario' ,include_in_schema=False)
    def scenario():
        g = planning.grid
        return dict(stops=[g.wire(*g.center((r,r))).model_dump() for r in [25,30,40,50,60,70,80,90]])
    mount_frontend(app,ROOT/'frontend/dist')
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__ == '__main__':
    main()
