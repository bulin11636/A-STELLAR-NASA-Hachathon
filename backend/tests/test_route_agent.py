"""Offline acceptance for dynamic ROI, ordered revisions and model accounting."""
import json
from pathlib import Path
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.api.errors import ApiProblem
from app.contracts.api import PlanRouteRequest
from app.coordinator.metered import MeteredProvider
from app.coordinator.route_agent import RouteAgent
from app.coordinator.settings import AgentSettings, environment
from app.main import create_app
from app.planning.grid import digest, transform_point
from app.planning.service import PlanningService
from test_planning import fixture_profile, request_for


def decision(action='replan', mode=None, waypoints=None, message='Terrain-only proposal; A* will validate the requested route.'):
    return dict(action=action,message=message,mode=mode,waypoints=waypoints,citations=['A1'])


def model_response(proposal):
    return dict(status='completed',output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
        usage=dict(input_tokens=500,input_tokens_details=dict(cached_tokens=100),output_tokens=100,
                   output_tokens_details=dict(reasoning_tokens=40)))


def configured(tmp_path, handler=None):
    planning=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    settings=AgentSettings(enabled=True,api_key='synthetic-test-key')
    provider=MeteredProvider(settings,planning.store.root,transport=httpx.MockTransport(handler or (lambda req:httpx.Response(200,json=model_response(decision())))))
    agent=RouteAgent(settings,planning,provider)
    return planning,agent,provider


def test_dynamic_crop_and_ordered_multi_leg_route(tmp_path):
    profile=fixture_profile(tmp_path,np.zeros((150,160)))
    raw=json.loads(profile.read_text()); raw['window']=[1,1,12,12]; profile.write_text(json.dumps(raw))
    planning=PlanningService('computed',profile,tmp_path/'routes')
    g=planning.grid
    # These points are deliberately outside the initial 12x12 window.
    far=g.wire(*(transform_point(g.transform,(110.5,100.5))))
    via=g.wire(*(transform_point(g.transform,(70.5,30.5))))
    request=request_for(g).model_copy(update={'goal':far,'waypoints':[via]})
    result=planning.plan(request)
    stored=planning.store.get(result.route_id)
    assert stored.metadata.grid.width>12 and stored.metadata.grid.height>12
    assert via in result.route
    assert result.route[0]==request.start and result.route[-1]==far
    assert stored.metadata.request.waypoints==[via]
    assert stored.metadata.rationale and '2 ordered route leg' in stored.metadata.rationale.facts[0]
    planning.grid.profile=planning.grid.profile.model_copy(update={'dynamic_windowing':False})
    with pytest.raises(ApiProblem,match='outside'):
        planning.plan(request)


def test_dynamic_crop_budget_and_source_coverage(tmp_path):
    profile=fixture_profile(tmp_path,np.zeros((150,160)))
    raw=json.loads(profile.read_text()); raw['window']=[1,1,10,10]; raw['adaptive_resolution']=False; raw['limits']={'max_grid_cells':100,'max_expanded_nodes':100,'max_elapsed_seconds':1}
    profile.write_text(json.dumps(raw))
    planning=PlanningService('computed',profile,tmp_path/'routes')
    request=request_for(planning.grid,a=(2,2),b=(8,8))
    far=planning.grid.wire(*(transform_point(planning.grid.transform,(100.5,100.5))))
    with pytest.raises(ApiProblem) as err: planning.plan(request.model_copy(update={'goal':far}))
    assert err.value.code=='PLANNING_LIMIT_EXCEEDED'
    with pytest.raises(ApiProblem) as err: planning.plan(request.model_copy(update={'goal':request.goal.model_copy(update={'longitude':0.0})}))
    assert err.value.code=='OUTSIDE_PLANNING_COVERAGE'


@pytest.mark.parametrize('corruption',['width','negative_resolution','affine'])
def test_semantic_record_corruption_rejected_with_refreshed_hash(tmp_path,corruption):
    planning=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    result=planning.plan(request_for(planning.grid))
    folder=planning.store.root/result.route_id
    record=json.loads((folder/'record.json').read_text())
    grid=record['metadata']['grid']
    if corruption=='width': grid['width']-=1
    elif corruption=='negative_resolution': grid['planning_resolution_m'][0]*=-1
    else: grid['affine'][2]+=20
    (folder/'record.json').write_text(json.dumps(record))
    manifest=json.loads((folder/'complete.json').read_text()); manifest['record.json']=digest(folder/'record.json')
    (folder/'complete.json').write_text(json.dumps(manifest))
    with pytest.raises(ApiProblem) as err: planning.store.get(result.route_id)
    assert err.value.code=='ROUTE_RECORD_INVALID'


def test_plan_route_runs_metered_a0_before_real_astar(tmp_path):
    planning,agent,provider=configured(tmp_path)
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        result=client.post('/api/v1/routes/plan',json=request_for(planning.grid).model_dump())
        assert result.status_code==200,result.text
        stored=client.get('/api/v1/routes/'+result.json()['route_id']).json()
        usage=stored['metadata']['usage']
        assert usage['model']=='gpt-6.1-sol' and usage['calls']==1
        assert usage['reasoning_tokens']==40
        assert usage['estimated_cost_usd']==pytest.approx((400*2+100*.1+100*10)/1e6)
        assert stored['metadata']['rationale']['model_commentary']
        invalid={**request_for(planning.grid).model_dump(),'start':{'longitude':0.0,'latitude':0.0}}
        assert client.post('/api/v1/routes/plan',json=invalid).status_code==400
        assert provider.totals()['attempts']==1  # invalid coverage must not make a paid attempt


def test_plan_route_accepts_an_explanation_only_model_proposal(tmp_path):
    planning,agent,provider=configured(tmp_path,lambda request:httpx.Response(200,json=model_response(decision('answer'))))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.post('/api/v1/routes/plan',json=request_for(planning.grid).model_dump())
    assert response.status_code==200,response.text
    assert planning.store.get(response.json()['route_id']).metadata.usage.calls==1
    assert provider.totals()['attempts']==1


def test_chat_answer_revision_idempotency_and_restart(tmp_path):
    count=0
    def handler(request):
        nonlocal count
        count+=1
        payload=json.loads(request.content)
        assert payload['reasoning']=={'effort':'medium'}
        assert payload['max_output_tokens']==4096
        message=json.loads(payload['input'][1]['content'])['message']
        answer=decision('answer',message='The current objective minimizes distance; environmental constraints remain unassessed.') if message=='Why?' else decision(mode='safest')
        return httpx.Response(200,json=model_response(answer))
    planning,agent,provider=configured(tmp_path,handler)
    result=planning.plan(request_for(planning.grid))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        url='/api/v1/routes/'+result.route_id+'/chat'
        request=dict(message='Why?',request_id='question-000000001')
        answer=client.post(url,json=request)
        assert answer.status_code==200,answer.text
        assert answer.json()['result'] is None
        assert client.post(url,json=request).json()==answer.json()
        assert count==1
        change=client.post(url,json=dict(message='Use safest',request_id='revision-000000001'))
        assert change.status_code==200,change.text
        body=change.json(); revised=body['result']
        assert revised['mode']=='safest' and revised['route_id']!=result.route_id
        assert body['metadata']['parent_route_id']==result.route_id
        assert planning.store.get(result.route_id).result==result
    # Fresh agent/store readers keep the completed history and revision links.
    with TestClient(create_app(planning=planning,route_agent=RouteAgent(agent.settings,planning,provider))) as client:
        history=client.get('/api/v1/routes/'+revised['route_id']+'/chat').json()['messages']
        assert [m['user_message'] for m in history]==['Why?','Use safest']
    assert provider.totals()['attempts']==2


def test_unrecognized_model_waypoint_and_failed_provider_preserve_old_route(tmp_path):
    proposal=decision(waypoints=[{'longitude':100.0,'latitude':20.0}])
    planning,agent,provider=configured(tmp_path,lambda req:httpx.Response(200,json=model_response(proposal)))
    result=planning.plan(request_for(planning.grid))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        url='/api/v1/routes/'+result.route_id+'/chat'
        bad=client.post(url,json=dict(message='Visit the unnamed hill',request_id='unknown-000000001'))
        assert bad.status_code==422 and bad.json()['error']['code']=='UNRESOLVED_WAYPOINT'
        assert planning.store.get(result.route_id).result==result
        replay=client.post(url,json=dict(message='Visit the unnamed hill',request_id='unknown-000000001'))
        assert replay.status_code==422 and replay.json()['error']['code']=='UNRESOLVED_WAYPOINT'
        assert replay.json()['error']['details'][0]['retry_allowed']=='false'
    assert provider.totals()['attempts']==1


def test_chat_adds_many_points_reorders_and_restores_complete_history(tmp_path):
    planning = PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    g = planning.grid
    stops = [g.wire(*g.center(cell)) for cell in [(2,4),(3,5),(4,6),(5,7),(6,8),(7,9),(8,8),(9,7)]]
    settings = AgentSettings(enabled=True,api_key='synthetic-test-key')
    def handler(req):
        message = json.loads(json.loads(req.content)['input'][1]['content'])['message']
        proposal = decision('answer') if message == 'Why this order?' else decision(waypoints=[p.model_dump() for p in (list(reversed(stops)) if message.startswith('Reverse') else stops)])
        return httpx.Response(200,json=model_response(proposal))
    provider = MeteredProvider(settings,tmp_path/'usage',httpx.MockTransport(handler))
    agent = RouteAgent(settings,planning,provider)
    initial = planning.plan(request_for(g).model_copy(update={'waypoints':stops[:2]}))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        add_request = dict(message='Add these points after the existing stops, in this order: '+ '; '.join(f'{p.longitude},{p.latitude}' for p in stops[2:]),request_id='add-many-points-0001')
        added = client.post('/api/v1/routes/'+initial.route_id+'/chat',json=add_request)
        assert added.status_code == 200, added.text
        body = added.json(); child = body['result']['route_id']
        assert body['metadata']['request']['waypoints'] == [p.model_dump() for p in stops]
        assert body['metadata']['parent_route_id'] == initial.route_id
        replay = client.post('/api/v1/routes/'+initial.route_id+'/chat',json=add_request)
        assert replay.json() == body
        reordered = client.post('/api/v1/routes/'+child+'/chat',json=dict(message='Reverse the order of all eight required waypoints; keep start and goal unchanged.',request_id='reverse-many-points-01'))
        assert reordered.status_code == 200, reordered.text
        revised = reordered.json(); grandchild = revised['result']['route_id']
        assert revised['metadata']['request']['waypoints'] == [p.model_dump() for p in reversed(stops)]
        answer = client.post('/api/v1/routes/'+grandchild+'/chat',json=dict(message='Why this order?',request_id='explain-new-order-0001'))
        assert answer.status_code == 200 and answer.json()['result'] is None
        request = request_for(g).model_dump(); request['waypoints'] = [p.model_dump() for p in stops]*2+[stops[0].model_dump()]
        assert client.post('/api/v1/routes/plan',json=request).status_code == 422
    fresh = RouteAgent(settings,PlanningService('computed',planning.profile_path,planning.store.root),provider)
    with TestClient(create_app(planning=fresh.planning,route_agent=fresh)) as client:
        history = client.get('/api/v1/routes/'+grandchild+'/chat').json()['messages']
        assert len(history) == 3
        assert client.get('/api/v1/routes/'+initial.route_id).json()['result'] == initial.model_dump(mode='json')
    assert provider.totals()['attempts'] == 3, 'Replay and invalid requests cannot add provider calls'


def test_request_budget_and_unknown_charges_are_persistent(tmp_path):
    settings=AgentSettings(enabled=True,api_key='test',max_calls=1)
    provider=MeteredProvider(settings,tmp_path,httpx.MockTransport(lambda req:httpx.Response(500,text='must never be logged')))
    with pytest.raises(ApiProblem) as err: provider.decide({'evidence':[]},'Plan')
    assert err.value.code=='A0_PROVIDER_ERROR'
    totals=provider.totals()
    assert totals['attempts']==1 and totals['estimated_or_reserved_usd']>0
    restarted=MeteredProvider(settings,tmp_path)
    with pytest.raises(ApiProblem) as err: restarted.decide({'evidence':[]},'Plan')
    assert err.value.code=='A0_BUDGET_EXHAUSTED'


def test_quota_error_is_actionable_and_never_retries(tmp_path):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(429,json={'error':{'code':'insufficient_quota','message':'untrusted provider error text'}})
    provider=MeteredProvider(AgentSettings(enabled=True,api_key='test'),tmp_path,httpx.MockTransport(handler))
    with pytest.raises(ApiProblem) as err: provider.decide({'evidence':[]},'Explain')
    assert err.value.code=='A0_QUOTA_EXHAUSTED'
    assert 'untrusted' not in err.value.message
    assert len(calls)==1 and provider.totals()['attempts']==1


@pytest.mark.parametrize('failure',['refusal','incomplete','invalid_arguments','missing_usage','timeout'])
def test_route_provider_failures_never_retry_or_change_the_previous_route(tmp_path,failure):
    calls = []
    def handler(req):
        calls.append(1)
        if failure == 'timeout': raise httpx.ReadTimeout('synthetic timeout',request=req)
        body = model_response(decision())
        if failure == 'refusal': body['output']=[dict(type='message',content=[dict(type='refusal',refusal='synthetic-only')])]
        elif failure == 'incomplete': body['status']='incomplete'
        elif failure == 'invalid_arguments': body['output'][0]['arguments']='{"action":"execute_arbitrary_code"}'
        elif failure == 'missing_usage': del body['usage']
        return httpx.Response(200,json=body)
    planning,agent,provider = configured(tmp_path,handler)
    previous = planning.plan(request_for(planning.grid))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        request = dict(message='Please reverse the stop order.',request_id='failed-proposal-0001')
        url = '/api/v1/routes/'+previous.route_id+'/chat'
        response = client.post(url,json=request)
        assert response.status_code == 503
        assert response.json()['error']['code'] in ('A0_PROVIDER_ERROR','A0_TIMEOUT')
        replay=client.post(url,json=request)
        assert replay.status_code == 503 and replay.json()['error']['code']==response.json()['error']['code']
        state=client.get(url+'/attempts/'+request['request_id']).json()
        assert state['state']==('unknown' if failure in ('timeout','missing_usage') else 'failed')
        assert state['retry_allowed'] is False
        assert client.get('/api/v1/routes/'+previous.route_id).json()['result'] == previous.model_dump(mode='json')
    assert len(calls) == 1 and provider.totals()['attempts'] == 1


def test_sixteen_stops_fit_the_existing_bounded_chat_context(tmp_path):
    planning = PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    stops = [planning.grid.wire(*planning.grid.center((r,c))) for r in [3,4,5,6] for c in [3,4,5,6]]
    settings = AgentSettings(enabled=True,api_key='synthetic-only')
    provider = MeteredProvider(settings,tmp_path/'usage',httpx.MockTransport(lambda req:httpx.Response(200,
        json=model_response(decision(waypoints=[p.model_dump() for p in reversed(stops)])))))
    agent = RouteAgent(settings,planning,provider)
    previous = planning.plan(request_for(planning.grid).model_copy(update={'waypoints':stops}))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response = client.post('/api/v1/routes/'+previous.route_id+'/chat',json=dict(message='Reverse all sixteen waypoint visits.',request_id='sixteen-stops-0001'))
        assert response.status_code == 200,response.text
        assert response.json()['metadata']['request']['waypoints'] == [p.model_dump() for p in reversed(stops)]
    assert provider.totals()['attempts'] == 1


def test_env_file_is_data_and_process_environment_has_precedence(tmp_path,monkeypatch):
    file=tmp_path/'settings.env'; file.write_text('OPENAI_API_KEY="synthetic-only"\nA_STELLAR_A0_MODEL=gpt-6.1-sol\n')
    monkeypatch.setenv('A_STELLAR_ENV_FILE',str(file))
    monkeypatch.setenv('A_STELLAR_A0_MODE','deterministic')
    config=AgentSettings.read(environment())
    assert config.api_key=='synthetic-only' and not config.enabled
    assert 'synthetic-only' not in repr(config)


def test_changed_or_removed_profile_never_spends_a_model_call(tmp_path):
    planning,agent,provider=configured(tmp_path)
    request=request_for(planning.grid)
    profile=Path(planning.profile_path)
    profile.write_text(profile.read_text()+'\n')
    with pytest.raises(ApiProblem) as err: agent.plan(request)
    assert err.value.code=='PLANNING_UNAVAILABLE'
    profile.unlink()
    with pytest.raises(ApiProblem) as err: agent.plan(request)
    assert err.value.code=='PLANNING_UNAVAILABLE'
    assert provider.totals()['attempts']==0
