#!/usr/bin/env python3
"""Stable P1 UI fixtures from the actual synthetic planner; zero model requests."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def export(destination):
    from app.agents.a3 import RadiationScenario,ScenarioRadiationWorker
    from app.agents.registry import WorkerRegistry
    from app.contracts.api import PlanRouteRequest,COORDINATE_SYSTEM
    from app.contracts.assessment import WalkingMission
    from app.contracts.workers import WorkerContext
    from app.coordinator.settings import AgentSettings
    from app.coordinator.route_agent import RouteAgent
    from app.planning.service import PlanningService
    from app.planning.synthetic_fixtures import inputs,controls
    from app.planning.policies import catalog
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    output={'policies.json':catalog()}
    with TemporaryDirectory(prefix='stellar-p1-fixture-') as temporary:
        folder=Path(temporary);profile=inputs(folder)
        planning=PlanningService('computed',profile,folder/'routes')
        agent=RouteAgent(AgentSettings(enabled=False),planning)
        registry=WorkerRegistry()
        scenario=RadiationScenario(scenario_id='synthetic-p1',roi_id='synthetic-roi',dataset_version='synthetic-v1',
            source=dict(dataset_id='synthetic-radiation',source_url='https://example.com/synthetic',mission='Synthetic',instrument='Synthetic'),
            source_locator='Synthetic fixture only',source_observation_period='Synthetic epoch',rate=12.0,rate_uncertainty=2.0,
            rate_unit='uSv/hour',uncertainty_description='Synthetic sensitivity band.',assumptions=['Constant synthetic rate.'],
            limitations=['No NASA or astronaut exposure data.'],max_duration_min=1440.0)
        registry.register(ScenarioRadiationWorker(scenario,'synthetic-scenario'))
        scope=WorkerContext(mission_id='synthetic',region_id='jezero',roi_id='synthetic-roi',dataset_version='synthetic-v1')
        agent.evidence=SimpleNamespace(registry=registry,scope=scope,input_hashes={'synthetic':'v1'})
        g=planning.grid
        base=PlanRouteRequest(region_id='jezero',coordinate_system=COORDINATE_SYSTEM,
            start=g.wire(*g.center((10,10))),goal=g.wire(*g.center((70,80))),mode='safest',
            mission_profile='balanced',mission=WalkingMission(speed_m_s=1.0,stop_minutes_per_waypoint=2.0,radiation_budget_usv=1000.0),
            waypoints=[g.wire(*g.center((30,30))),g.wire(*g.center((50,50)))])
        def record(name,request,service=planning,coordinator=agent):
            result=coordinator.plan(request);stored=service.store.get(result.route_id)
            output[name+'.json']=stored.model_dump(mode='json')
        for profile_id in ('safest','fastest','science_priority','balanced'):
            for resolution in ('coarse','standard','fine'):
                record('profile-'+profile_id+'-'+resolution,base.model_copy(update=dict(mission_profile=profile_id,
                    mode='shortest' if profile_id=='fastest' else 'safest',resolution_profile=resolution)))
        record('low-risk-low-confidence',base)
        record('blocked-scenario',base.model_copy(update={'mission':base.mission.model_copy(update={'radiation_budget_usv':0.0})}))
        record('required-thermal-unassessed',base.model_copy(update={'mission':base.mission.model_copy(update={'required_analyses':['A2']})}))
        agent.evidence=SimpleNamespace(registry=WorkerRegistry(),scope=scope,input_hashes={'synthetic':'missing'})
        record('missing-radiation',base)
        # A fresh explicitly synthetic fixture service alone can produce a verified test outcome.
        controls(g,folder)
        body=json.loads(profile.read_text());body['registration_controls']='controls.json'
        verified_profile=folder/'verified-profile.json';verified_profile.write_text(json.dumps(body))
        verified=PlanningService('computed',verified_profile,folder/'verified-routes',allow_synthetic_registration=True)
        fixture_agent=RouteAgent(AgentSettings(enabled=False),verified)
        fixture_agent.evidence=SimpleNamespace(registry=registry,scope=scope,input_hashes={'synthetic':'v1'})
        record('verified-alignment-synthetic',base,verified,fixture_agent)
        output['unverified-alignment.json']=output['profile-balanced-standard.json']
        # Route IDs, elapsed timings, timestamps and private-file digests are normalized.
        # Geometry, policies, factor values, controls and source hashes are actual synthetic outputs.
        for name,value in output.items():
            old=value.get('result',{}).get('route_id') if isinstance(value,dict) else None
            fixed='route-'+hashlib.sha256(name.encode()).hexdigest()[:32]
            def stable(item):
                if isinstance(item,dict):
                    return {k:('2026-11-15T00:00:00Z' if k=='created_at' else 0.0 if k=='elapsed_ms' else stable(v)) for k,v in item.items()}
                if isinstance(item,list): return [stable(v) for v in item]
                if isinstance(item,float):
                    # Eliminate machine-level representation noise in derived
                    # percentage values without degrading geospatial precision.
                    rounded=round(item,8)
                    return rounded if abs(item-rounded)<1e-12 else item
                if isinstance(item,str) and old: return item.replace(old,fixed)
                return item
            item=stable(value)
            if old:
                for role,artifact in item['metadata']['artifacts'].items():
                    artifact['sha256']=hashlib.sha256((name+':'+role).encode()).hexdigest()
            (destination/name).write_text(json.dumps(item,indent=2,allow_nan=False)+'\n')
        gc.collect()
    return sorted(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'data/fixtures/p1')
    args=parser.parse_args()
    print(json.dumps(dict(files=export(args.output_dir),live_model_calls=0),indent=2))
