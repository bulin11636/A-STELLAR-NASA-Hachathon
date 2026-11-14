"""Local browser-test fixture: real DEM and host planner, explicitly mocked model."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

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
    def handler(req):
        mission = json.loads(json.loads(req.content)['input'][1]['content'])
        message = mission['message']
        before = mission['mission']['request']['waypoints']
        waypoints = None
        if message.startswith('Add required points:'):
            waypoints = before + [dict(longitude=float(x),latitude=float(y)) for x,y in re.findall(r'(\d+\.\d+)\s*,\s*(\d+\.\d+)',message)]
        if message.startswith('Reverse all waypoint visits'):
            waypoints = list(reversed(before))
        proposal = dict(action='answer' if message.startswith('Why') else 'replan',
            message='Mock A0 proposal: the host validates terrain routing and preserves exact required stop order.',
            mode=None,waypoints=waypoints,citations=['A1'])
        return httpx.Response(200,json=dict(status='completed',output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
            usage=dict(input_tokens=500,output_tokens=100)))
    settings = AgentSettings(enabled=True,api_key='synthetic-browser-key')
    provider = MeteredProvider(settings,args.run_dir/'mock-usage',httpx.MockTransport(handler))
    app = create_app(planning=planning,route_agent=RouteAgent(settings,planning,provider))
    @app.get('/__test/scenario',include_in_schema=False)
    def scenario():
        g = planning.grid
        return dict(stops=[g.wire(*g.center((r,r))).model_dump() for r in [25,30,40,50,60,70,80,90]])
    mount_frontend(app,ROOT/'frontend/dist')
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__ == '__main__':
    main()
