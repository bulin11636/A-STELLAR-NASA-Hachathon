"""Real planner policy selection, formula boundaries and durable P1 invariants."""
import json
from datetime import datetime,timezone
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.agents.a3 import ScenarioRadiationWorker
from app.agents.registry import WorkerRegistry
from app.contracts.api import PlanRouteRequest
from app.contracts.assessment import WalkingMission, EvidenceQuality, RiskFactor, RouteAssessment
from app.contracts.routes import StoredRouteResponse
from app.contracts.workers import WorkerContext
from app.coordinator.route_agent import RouteAgent
from app.coordinator.settings import AgentSettings
from app.main import create_app
from app.planning.grid import load_grid
from app.planning.policies import catalog,mission_profile
from app.planning.risk_assessment import fuse,terrain_factor
from app.planning.service import PlanningService
from app.planning.synthetic_fixtures import inputs
from test_planning import request_for
from test_radiation import scenario


def prepared(tmp_path,*,radiation=True):
    path=inputs(tmp_path);planning=PlanningService('computed',path,tmp_path/'routes')
    agent=RouteAgent(AgentSettings(enabled=False),planning)
    registry=WorkerRegistry()
    if radiation: registry.register(ScenarioRadiationWorker(scenario(),'synthetic-scenario'))
    agent.evidence=SimpleNamespace(registry=registry,scope=WorkerContext(mission_id='p1',region_id='jezero',roi_id='test-roi',dataset_version='test-v1'),input_hashes={'synthetic':'v1'})
    return planning,agent


@pytest.mark.parametrize('profile',['safest','fastest','science_priority','balanced'])
@pytest.mark.parametrize('resolution',['coarse','standard','fine'])
def test_profiles_apply_actual_cost_resolution_and_survive_restart(tmp_path,profile,resolution):
    planning,agent=prepared(tmp_path)
    mode='shortest' if profile=='fastest' else 'safest'
    request=request_for(planning.grid,a=(10,10),b=(70,80),mode=mode).model_copy(update={
        'mission_profile':profile,'resolution_profile':resolution,'mission':WalkingMission(speed_m_s=1.0,radiation_budget_usv=1000.0)})
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        key='p1-profile-'+profile+'-'+resolution
        response=client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key})
        assert response.status_code==200,response.text
        result=response.json();record=planning.store.get(result['route_id'])
        p=record.metadata.planning_policy;a=record.metadata.assessment
        assert p.mission_profile_version==profile+'-v2' and p.resolution_profile==resolution
        expected={'safest':6.0,'fastest':0.0,'science_priority':2.0,'balanced':4.0}[profile]
        assert p.terrain_weight==expected
        assert a.hard_gate_status=='pass' and 0<=a.risk_score<=100 and 0<=a.assessment_confidence<=100
        assert record.result.metrics.risk_score is None  # legacy score never carries a percent
        assert len(a.risk_factors)==6 and a.risk_factors[4].agent_id=='A5'
        assert a.risk_factors[4].status=='not_applicable'
        assert p.actual_cell_size_m[0]>=20 and p.actual_native_factor>=(2 if resolution=='coarse' else 1)
        assert p.limits.max_grid_cells<=planning.grid.profile.limits.max_grid_cells
    fresh=PlanningService('computed',planning.profile_path,planning.store.root)
    with TestClient(create_app(planning=fresh)) as client:
        assert client.get('/api/v1/routes/'+result['route_id']).json()==record.model_dump(mode='json')
        assert client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key}).json()==result


def test_missing_factor_and_failed_budget_override_weighted_ranking(tmp_path):
    planning,agent=prepared(tmp_path,radiation=False)
    request=request_for(planning.grid).model_copy(update={'mission':WalkingMission(speed_m_s=1.0)})
    record=planning.store.get(agent.plan(request).route_id)
    assert record.metadata.assessment.hard_gate_status=='unassessed' and record.metadata.assessment.risk_score is None
    assert next(f for f in record.metadata.assessment.risk_factors if f.agent_id=='A3').confidence_contribution==0
    agent.evidence.registry.register(ScenarioRadiationWorker(scenario(),'synthetic-scenario'))
    request=request.model_copy(update={'mission':WalkingMission(speed_m_s=1.0,radiation_budget_usv=0.0)})
    blocked=planning.store.get(agent.plan(request).route_id)
    assert blocked.metadata.assessment.hard_gate_status=='blocked' and blocked.metadata.assessment.risk_score is None
    assert blocked.metadata.assessment.assessment_confidence is not None


def test_policy_catalog_immutable_weights_and_bad_input(tmp_path):
    planning,agent=prepared(tmp_path)
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        result=client.get('/api/v1/planning/policies')
        assert result.status_code==200 and len(result.json()['profiles'])==4
        assert len(result.json()['resolutions'])==3
        request=request_for(planning.grid).model_dump(mode='json')
        for field,value in [('mission_profile','invented'),('resolution_profile','ultra'),('risk_weights',{'A1':1})]:
            assert client.post('/api/v1/routes/plan',json={**request,field:value}).status_code==422
        bad=client.post('/api/v1/routes/plan',json={**request,'mission_profile':'safest'})
        assert bad.status_code==422 and bad.json()['error']['code']=='PROFILE_OBJECTIVE_MISMATCH'
        outside=client.post('/api/v1/routes/plan',json={**request,'start':{'longitude':0.0,'latitude':0.0}})
        assert outside.status_code==400 and outside.json()['error']['details'][0]['hard_gate_status']=='blocked'
    p=mission_profile('balanced');raw=p.model_dump();raw['risk_weights']['A1']-=.1;raw['risk_weights']['A3']+=.1
    with pytest.raises(ValidationError): type(p).model_validate(raw)
    p.risk_weights['A1']=0
    assert mission_profile('balanced').risk_weights['A1']==.85


def test_formula_boundaries_and_missing_factor_never_becomes_zero():
    q=EvidenceQuality(availability=1,route_coverage=1,temporal_applicability=1,validation_provenance=1)
    zero=EvidenceQuality(availability=0,route_coverage=0,temporal_applicability=0,validation_provenance=0)
    for value in [0.0,1.0]:
        factors=[RiskFactor(agent_id=a,kind='risk',status='assessed',risk_score=value,evidence_quality=q,evidence_ids=['synthetic:'+a],message='Synthetic factor.') if a in ('A1','A3') else
            RiskFactor(agent_id=a,kind='context',status='not_applicable' if a=='A5' else 'unavailable',evidence_quality=zero,message='Unavailable synthetic context.') for a in ('A1','A2','A3','A4','A5','A6')]
        result=fuse(RouteAssessment(),mission_profile('balanced'),factors)
        assert result.risk_score==value*100
        assert result.assessment_confidence==pytest.approx(65.0)
        raw=result.model_dump();raw['assessment_confidence']+=1
        with pytest.raises(ValidationError): RouteAssessment.model_validate(raw)
        factors[2]=RiskFactor(agent_id='A3',kind='risk',status='unavailable',evidence_quality=zero,message='Missing.')
        assert fuse(RouteAssessment(),mission_profile('balanced'),factors).risk_score is None


def test_old_score_scale_and_stale_terrain_do_not_create_new_confidence(tmp_path):
    legacy={'mission_profile':dict(profile_id='balanced',version='balanced-v1',risk_weights=mission_profile('balanced').risk_weights,confidence_weights=mission_profile('balanced').confidence_weights),'assessment_confidence':.45}
    assert RouteAssessment.model_validate(legacy).assessment_confidence==45
    path=inputs(tmp_path);raw=json.loads(path.read_text());raw['acquisition_time']='2000-01-01T00:00:00Z';path.write_text(json.dumps(raw))
    grid=load_grid(path)
    factor=terrain_factor(grid,[(10,10)],['synthetic-grid'],now=datetime(2026,11,15,tzinfo=timezone.utc))
    assert factor.status=='stale' and factor.risk_score is None and factor.confidence_contribution==0
    assert factor.evidence_quality.availability==1 and factor.evidence_quality.temporal_applicability==0


def test_explicit_blocked_gate_and_storage_corruption_cannot_be_ranked(tmp_path):
    planning,agent=prepared(tmp_path)
    request=request_for(planning.grid).model_copy(update={'mission':WalkingMission(speed_m_s=1.0,radiation_budget_usv=1000.0)})
    result=agent.plan(request);record=planning.store.get(result.route_id)
    blocked=fuse(RouteAssessment(hard_gate_status='blocked'),record.metadata.assessment.mission_profile,record.metadata.assessment.risk_factors)
    assert blocked.hard_gate_status=='blocked' and blocked.risk_score is None
    for change in ['confidence','profile','legs','resolution']:
        raw=record.model_dump()
        if change=='confidence': raw['metadata']['assessment']['risk_factors'][0]['confidence_contribution']+=1
        if change=='profile': raw['metadata']['assessment']['mission_profile']['risk_weights']['A1']=.2
        if change=='legs': raw['metadata']['legs'][0]['distance_m']+=20
        if change=='resolution': raw['metadata']['planning_policy']['actual_cell_size_m']=(1.0,1.0)
        with pytest.raises(ValidationError): StoredRouteResponse.model_validate(raw)


def test_low_confidence_has_an_actionable_reason_and_evidence_components(tmp_path):
    planning,agent=prepared(tmp_path)
    request=request_for(planning.grid).model_copy(update={'mission':WalkingMission(speed_m_s=1.0,radiation_budget_usv=1000.0)})
    record=planning.store.get(agent.plan(request).route_id)
    assessment=record.metadata.assessment
    assert assessment.hard_gate_status=='pass' and assessment.assessment_confidence<70
    assert any('below 70' in text and 'acquisition' in text for text in assessment.limitations)
    assert next(f for f in assessment.risk_factors if f.agent_id=='A1').evidence.route_coverage_fraction==1
    radiation=next(f for f in assessment.risk_factors if f.agent_id=='A3')
    assert radiation.evidence.observation_period=='synthetic epoch'
    assert radiation.evidence.source_urls==['https://example.com/synthetic']


def test_completed_v1_request_with_omitted_profile_replays_without_replanning(tmp_path):
    from app.coordinator.attempts import save_json,payload_hash
    from app.planning.grid import digest
    planning,agent=prepared(tmp_path)
    request=request_for(planning.grid)
    result=planning.plan(request)
    folder=planning.store.root/result.route_id
    raw=json.loads((folder/'record.json').read_text())
    meta=raw['metadata'];meta['request']['mission_profile']='balanced';meta['request'].pop('resolution_profile')
    a=meta['assessment'];a['mission_profile']=mission_profile('balanced').model_dump();a['mission_profile']['version']='balanced-v1'
    a['assessment_confidence']=.45;a['hard_gate_status']='pass';a['risk_factors']=[]
    for key in ('schema_version','formula_version','score_scale','gate_reasons'): a.pop(key,None)
    for key in ('planning_policy','legs','registration'): meta.pop(key,None)
    (folder/'record.json').write_text(json.dumps(raw))
    manifest=json.loads((folder/'complete.json').read_text());manifest['record.json']=digest(folder/'record.json');(folder/'complete.json').write_text(json.dumps(manifest))
    old=planning.store.get(result.route_id)
    assert old.metadata.assessment.assessment_confidence==45
    from app.coordinator.plan_requests import PlanRequests
    requests=PlanRequests(agent);key='p1-v1-compatibility-001'
    record_path,response_path,_=requests.attempts.paths(key)
    save_json(record_path,dict(schema_version=1,payload_hash=payload_hash(old.metadata.request.model_dump(mode='json',exclude_none=True)),
        state='succeeded',attempt=1,updated_at='2026-11-15T00:00:00Z',failure=None))
    save_json(response_path,result.model_dump(mode='json'))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.post('/api/v1/routes/plan',json=request.model_dump(mode='json'),headers={'Idempotency-Key':key})
        assert response.status_code==200,response.text
        assert response.json()['route_id']==result.route_id
        assert client.get('/api/v1/routes/requests/'+key).json()['state']=='succeeded'


def test_private_audit_stays_bound_to_public_assessment(tmp_path):
    from app.planning.grid import digest
    from app.api.errors import ApiProblem
    planning,agent=prepared(tmp_path)
    result=agent.plan(request_for(planning.grid))
    folder=planning.store.root/result.route_id
    raw=json.loads((folder/'record.json').read_text());raw['metadata']['assessment']['limitations'].append('Changed audit text')
    (folder/'record.json').write_text(json.dumps(raw))
    manifest=json.loads((folder/'complete.json').read_text());manifest['record.json']=digest(folder/'record.json');(folder/'complete.json').write_text(json.dumps(manifest))
    with pytest.raises(ApiProblem) as error: planning.store.get(result.route_id)
    assert error.value.code=='ROUTE_RECORD_INVALID'


def test_incompatible_radiation_scope_is_visible_and_never_scored(tmp_path):
    planning,agent=prepared(tmp_path,radiation=False)
    agent.evidence.registry.register(ScenarioRadiationWorker(scenario(roi_id='another-roi'),'synthetic-incompatible-scenario'))
    request=request_for(planning.grid).model_copy(update={'mission':WalkingMission(speed_m_s=1.0,radiation_budget_usv=1000.0)})
    record=planning.store.get(agent.plan(request).route_id)
    factor=next(f for f in record.metadata.assessment.risk_factors if f.agent_id=='A3')
    assert factor.status=='incompatible' and factor.risk_score is None and factor.confidence_contribution==0
    assert record.metadata.assessment.hard_gate_status=='unassessed' and record.metadata.assessment.risk_score is None
