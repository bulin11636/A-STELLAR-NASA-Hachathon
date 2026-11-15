"""Offline routing, restart, evidence and walking-assumption acceptance."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.a3 import ScenarioRadiationWorker
from app.agents.registry import WorkerRegistry
from app.contracts.assessment import WalkingMission
from app.contracts.routes import StoredRouteResponse
from app.contracts.workers import ScienceResult, ThermalResult, WorkerContext
from app.coordinator.metered import MeteredProvider
from app.coordinator.route_agent import RouteAgent
from app.coordinator.settings import AgentSettings
from app.main import create_app
from app.planning.service import PlanningService
from test_planning import fixture_profile, request_for
from test_radiation import scenario
from test_route_agent import decision, model_response


class Science:
    agent_id='A4'
    calls=0
    async def run(self, context):
        self.calls+=1
        return ScienceResult(status='partial',data_kind='observed',dataset_ids=['test-catalog'],
            provenance_ref='synthetic-catalog',warnings=['Unranked synthetic science sites.'])


class Broken:
    agent_id='A6'
    async def run(self, context):
        raise RuntimeError('Synthetic worker failure')


class Thermal:
    agent_id='A2'
    async def run(self, context):
        return ThermalResult(status='partial',data_kind='scenario',dataset_ids=['synthetic-thermal'],
            provenance_ref='synthetic-thermal-config',warnings=['Uncalibrated visual mosaic.'])


def setup(tmp_path, *, selected=('A4',), workers=None, callback=None, enabled=True):
    planning=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    settings=AgentSettings(enabled=enabled,api_key='offline-test-only',usage_root=tmp_path/'usage')
    calls=[]
    def handler(req):
        body=json.loads(req.content); name=body['tool_choice']['name'];calls.append(name)
        if callback:
            override=callback(body,calls)
            if override is not None: return override
        if name=='select_route_specialists':
            response=model_response(dict(choices=[dict(agent_id=a,selected=a in selected,reason='Synthetic selection reason.') for a in ('A2','A3','A4','A6')]))
            response['output'][0]['name']=name
            return httpx.Response(200,json=response)
        message=json.loads(body['input'][1]['content'])['message']
        return httpx.Response(200,json=model_response(decision('answer' if message=='Why?' else 'replan')))
    provider=MeteredProvider(settings,tmp_path/'usage',httpx.MockTransport(handler))
    agent=RouteAgent(settings,planning,provider)
    registry=WorkerRegistry()
    for worker in workers if workers is not None else [Science()]: registry.register(worker)
    agent.evidence=SimpleNamespace(registry=registry,scope=WorkerContext(mission_id='test',region_id='jezero',
        roi_id='test-roi',dataset_version='test-v1'),input_hashes={'synthetic':'v1'})
    return planning,agent,provider,calls


def trace(record,agent): return next(t for t in record.metadata.specialist_trace if t.agent_id==agent)


def test_selection_executes_only_chosen_tools_and_caches_versioned_outputs(tmp_path):
    worker=Science()
    planning,agent,provider,calls=setup(tmp_path,workers=[worker,Broken()])
    request=request_for(planning.grid)
    first=planning.store.get(agent.plan(request).route_id)
    assert calls==['select_route_specialists','propose_route_action']
    assert first.metadata.usage.calls==2
    assert trace(first,'A1').required and trace(first,'A1').application=='terrain_cost'
    assert trace(first,'A4').execution_state=='succeeded' and trace(first,'A4').application=='context_only'
    assert not trace(first,'A6').selected and trace(first,'A6').execution_state=='not_requested'
    assert worker.calls==1 and trace(first,'A4').artifact_id.endswith(':provenance#A4')
    second=planning.store.get(agent.plan(request).route_id)
    assert trace(second,'A4').execution_state=='cached' and worker.calls==1
    agent.evidence.input_hashes={'synthetic':'v2'}
    third=planning.store.get(agent.plan(request).route_id)
    assert trace(third,'A4').execution_state=='succeeded' and worker.calls==2
    assert provider.totals()['attempts']==6


def test_required_tools_cannot_be_omitted_and_missing_analysis_never_passes(tmp_path):
    planning,agent,_,_=setup(tmp_path,selected=(),workers=[Science(),Thermal()])
    mission=WalkingMission(required_analyses=['A2','A3','A4'])
    record=planning.store.get(agent.plan(request_for(planning.grid).model_copy(update={'mission':mission})).route_id)
    assert all(trace(record,a).selected and trace(record,a).required for a in mission.required_analyses)
    assert trace(record,'A2').application=='context_only'
    assert trace(record,'A3').execution_state=='unavailable'
    assert record.metadata.assessment.required_unassessed==['A2','A3']
    assert record.metadata.assessment.dose_estimate_usv is None
    assert record.result.metrics.risk_score is None
    assert any('provisional' in text for text in record.result.warnings)


def test_failed_workers_are_isolated_and_uncitable(tmp_path):
    seen=[]
    def inspect(body,calls):
        if calls[-1]=='propose_route_action':
            seen.append(json.loads(body['input'][1]['content'])['mission'])
            if len(calls)>2:
                proposal=decision('answer');proposal['citations']=['A6']
                return httpx.Response(200,json=model_response(proposal))
    planning,agent,_,_=setup(tmp_path,selected=('A6',),workers=[Broken()],callback=inspect)
    result=planning.store.get(agent.plan(request_for(planning.grid)).route_id)
    assert trace(result,'A6').execution_state=='failed' and trace(result,'A6').application=='none'
    assert next(e for e in seen[0]['evidence'] if e['id']=='A6')['status']=='unavailable'
    with pytest.raises(Exception) as error:
        agent.provider.decide({'evidence':[{'id':'A6','status':'failed','kind':'observed'}]},'Why?')
    assert error.value.code=='A0_PROVIDER_ERROR'


def test_selection_checkpoint_survives_final_429_and_restart_without_duplicate_selection(tmp_path):
    def reject(body,calls):
        if len(calls)==2: return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded'}})
    planning,agent,provider,calls=setup(tmp_path,callback=reject)
    request=request_for(planning.grid).model_dump(mode='json');key='specialist-retry-0001'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        failed=client.post('/api/v1/routes/plan',json=request,headers={'Idempotency-Key':key})
        assert failed.status_code==503,failed.text
        assert client.post('/api/v1/routes/plan',json=request,headers={'Idempotency-Key':key}).status_code==503
        assert len(calls)==2
    fresh=RouteAgent(agent.settings,planning,provider);fresh.evidence=agent.evidence
    with TestClient(create_app(planning=planning,route_agent=fresh)) as client:
        response=client.post('/api/v1/routes/plan',json=request,headers={'Idempotency-Key':key,'X-A-Stellar-Retry-Attempt':'1'})
        assert response.status_code==200,response.text
        record=planning.store.get(response.json()['route_id'])
        assert record.metadata.usage.calls==2
    assert calls==['select_route_specialists','propose_route_action','propose_route_action']
    assert provider.totals()['attempts']==3


def test_invalid_selector_is_rejected_before_workers_or_final_generation(tmp_path):
    worker=Science()
    def malformed(body,calls):
        response=model_response(dict(choices=[dict(agent_id='A4',selected=True,reason='Invalid duplicates')]*4))
        response['output'][0]['name']='select_route_specialists'
        return httpx.Response(200,json=response)
    planning,agent,_,calls=setup(tmp_path,workers=[worker],callback=malformed)
    with pytest.raises(Exception) as error: agent.plan(request_for(planning.grid))
    assert error.value.code=='A0_PROVIDER_ERROR'
    assert len(calls)==1 and worker.calls==0


def test_deterministic_required_execution_capabilities_and_legacy_hash(tmp_path):
    worker=Science()
    planning,agent,_,calls=setup(tmp_path,enabled=False,workers=[worker])
    body=request_for(planning.grid).model_dump(mode='json');body.pop('mission')
    body['mission']={'required_analyses':['A4']}
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        caps=client.get('/api/v1/a0/capabilities').json()
        assert caps['mission_mode']=='walking' and len(caps['capabilities'])==5
        assert caps['merged_capabilities'][0]['merged_into']=='A1'
        response=client.post('/api/v1/routes/plan',json=body,headers={'Idempotency-Key':'walking-offline-0001'})
        assert response.status_code==200,response.text
        assert trace(planning.store.get(response.json()['route_id']),'A4').execution_state=='succeeded'
        legacy={**body};legacy.pop('mission')
        first=client.post('/api/v1/routes/plan',json=legacy,headers={'Idempotency-Key':'legacy-mission-0001'})
        legacy['mission']=None
        assert client.post('/api/v1/routes/plan',json=legacy,headers={'Idempotency-Key':'legacy-mission-0001'}).json()==first.json()
    assert calls==[] and worker.calls==1


@pytest.mark.parametrize('override', [None,0.0,60.0])
def test_walking_time_and_duration_drive_scoped_radiation_after_astar(tmp_path,override):
    worker=ScenarioRadiationWorker(scenario(),'synthetic-scenario')
    planning,agent,_,_=setup(tmp_path,selected=(),workers=[worker])
    stops=[planning.grid.wire(*planning.grid.center(cell)) for cell in [(2,8),(8,2)]]
    request=request_for(planning.grid).model_copy(update={'waypoints':stops,'mission':WalkingMission(
        speed_m_s=1.0,stop_minutes_per_waypoint=3.0,exposure_duration_min=override,radiation_budget_usv=0.0)})
    record=planning.store.get(agent.plan(request).route_id)
    expected=record.result.metrics.distance_m/60+6
    assessment=record.metadata.assessment
    assert record.result.metrics.estimated_time_min==pytest.approx(expected)
    assert assessment.time.stop_min==6
    duration=override if override is not None else expected
    assert assessment.radiation_duration_min==duration
    assert assessment.dose_estimate_usv==pytest.approx(duration*12/60)
    assert trace(record,'A3').application=='dose_scenario'
    assert assessment.required_failed==(['A3'] if duration else [])
    assert assessment.radiation_constraint_status==('fail' if duration else 'pass')
    assert record.result.metrics.risk_score is None
    tampered=record.model_dump();tampered['result']['metrics']['estimated_time_min']+=1
    with pytest.raises(ValidationError): StoredRouteResponse.model_validate(tampered)


def test_unknown_time_without_speed_and_direct_planner_required_unknown(tmp_path):
    planning,agent,_,_=setup(tmp_path,enabled=False,workers=[])
    request=request_for(planning.grid).model_copy(update={'mission':WalkingMission(stop_minutes_per_waypoint=5.0,required_analyses=['A3'])})
    record=planning.store.get(planning.plan(request).route_id)
    assert record.result.metrics.estimated_time_min is None
    assert record.metadata.assessment.radiation_duration_min is None
    assert record.metadata.assessment.required_unassessed==['A3']


def test_chat_revisions_preserve_assumptions_recompute_time_and_persist_trace(tmp_path):
    points=[]
    def revise(body,calls):
        if calls[-1]=='propose_route_action':
            message=json.loads(body['input'][1]['content'])['message']
            if message.startswith('Add'):
                return httpx.Response(200,json=model_response(decision(waypoints=points)))
    planning,agent,provider,calls=setup(tmp_path,callback=revise)
    points.extend(planning.grid.wire(*planning.grid.center(cell)).model_dump() for cell in [(2,8),(8,2)])
    request=request_for(planning.grid).model_copy(update={'mission':WalkingMission(speed_m_s=1.0,stop_minutes_per_waypoint=4.0)})
    previous=agent.plan(request)
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        url='/api/v1/routes/'+previous.route_id+'/chat'
        answer=client.post(url,json=dict(message='Why?',request_id='specialist-question-001'))
        assert answer.status_code==200,answer.text
        assert answer.json()['result'] is None and len(answer.json()['specialist_trace'])==5
        evidence=planning.store.root/'requests'/'chat'/previous.route_id/'specialist-question-001.evidence'
        assert 'A4' in json.loads(evidence.read_text())['results']
        message='Add '+ '; '.join(f"{p['longitude']},{p['latitude']}" for p in points)
        revised=client.post(url,json=dict(message=message,request_id='specialist-revision-001'))
        assert revised.status_code==200,revised.text
        child=revised.json()
        assert child['metadata']['request']['mission']==request.mission.model_dump()
        assert child['result']['metrics']['estimated_time_min']==pytest.approx(child['result']['metrics']['distance_m']/60+8)
        assert child['metadata']['specialist_trace']==child['specialist_trace']
        assert client.get(url).json()['messages'][-1]==child
    assert len(calls)==6 and provider.totals()['attempts']==6


@pytest.mark.parametrize('mission',[{'mode':'rover'},{'speed_m_s':0},{'speed_m_s':True},{'speed_m_s':21},
    {'speed_m_s':float('nan')},{'stop_minutes_per_waypoint':-1},{'required_analyses':['A1']},
    {'required_analyses':['A2','A2']},{'exposure_duration_min':10081},{'radiation_budget_usv':-1}])
def test_invalid_walking_assumptions_are_rejected(mission):
    with pytest.raises(ValidationError): WalkingMission(**mission)


def test_chat_retry_reuses_selection_after_fresh_agent_and_corrupt_checkpoint_blocks_calls(tmp_path):
    def reject(body,calls):
        if len(calls)==2: return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded'}})
    planning,agent,provider,calls=setup(tmp_path,callback=reject)
    previous=planning.plan(request_for(planning.grid))
    body=dict(message='Why?',request_id='chat-selection-retry-001')
    url='/api/v1/routes/'+previous.route_id+'/chat'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.post(url,json=body)
        assert response.status_code==503,response.text
        assert planning.store.get(previous.route_id).result==previous
    fresh=RouteAgent(agent.settings,planning,provider);fresh.evidence=agent.evidence
    with TestClient(create_app(planning=planning,route_agent=fresh)) as client:
        response=client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'})
        assert response.status_code==200,response.text
        assert response.json()['usage']['calls']==2
        assert response.json()['result'] is None
    assert calls==['select_route_specialists','propose_route_action','propose_route_action']
    key='corrupt-selection-0001'
    request=request_for(planning.grid)
    agent.plan(request,request_id=key)
    path=planning.store.root/'requests'/'plans'/(key+'.selection')
    data=json.loads(path.read_text());data['input_hash']='corrupt';path.write_text(json.dumps(data))
    before=len(calls)
    with pytest.raises(Exception) as error: agent.plan(request,request_id=key)
    assert error.value.code=='A0_SELECTION_RECORD_INVALID' and len(calls)==before


def test_cache_invalidates_when_configured_raster_changes(tmp_path):
    worker=Science();raster=tmp_path/'synthetic-raster';raster.write_bytes(b'initial')
    worker.config=SimpleNamespace(day_path=raster)
    planning,agent,_,_=setup(tmp_path,workers=[worker])
    request=request_for(planning.grid)
    agent.plan(request);agent.plan(request)
    assert worker.calls==1
    raster.write_bytes(b'new synthetic raster bytes')
    agent.plan(request)
    assert worker.calls==2
