"""Observable request outcomes, explicit retries, restarts and competing workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
from threading import Event

from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.errors import ApiProblem
from app.contracts.chat import ChatRequest
from app.coordinator.attempts import AttemptStore, Record, now, payload_hash, save_json
from app.coordinator.chat import RouteChat
from app.coordinator.metered import MeteredProvider
from app.coordinator.route_agent import RouteAgent
from app.coordinator.settings import AgentSettings
from app.main import create_app
from app.planning.service import PlanningService
from test_planning import fixture_profile,request_for
from test_route_agent import decision,model_response


def setup(tmp_path,handler):
    planning=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    settings=AgentSettings(enabled=True,api_key='synthetic-only',usage_root=tmp_path/'usage')
    provider=MeteredProvider(settings,settings.usage_root,httpx.MockTransport(handler))
    agent=RouteAgent(settings,planning,provider)
    previous=planning.plan(request_for(planning.grid))
    return planning,agent,provider,previous


def answer():
    return httpx.Response(200,json=model_response(decision('answer')))


def test_rejected_chat_is_cached_and_only_an_explicit_retry_executes(tmp_path):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(429,json={'error':{'code':'credit_balance_exhausted','message':'NEVER-STORE-CREDENTIAL'}}) if len(calls)==1 else answer()
    planning,agent,provider,previous=setup(tmp_path,handler)
    body=dict(request_id='recover-chat-request-01',message='Why this route?')
    url='/api/v1/routes/'+previous.route_id+'/chat'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        failed=client.post(url,json=body)
        assert failed.status_code==503 and failed.json()['error']['code']=='A0_CREDIT_BALANCE_EXHAUSTED'
        assert client.post(url,json=body).json()==failed.json()
        status_response=client.get(url+'/attempts/'+body['request_id'])
        assert status_response.headers['cache-control']=='no-store'
        state=status_response.json()
        assert (state['state'],state['attempt'],state['retry_allowed'])==('failed',1,True)
        assert client.post(url,json={**body,'message':'Different text'}).json()['error']['code']=='CHAT_REQUEST_CONFLICT'
        assert len(calls)==1
    # A restarted application can recover explicitly, with the original body/ID.
    fresh=RouteAgent(agent.settings,planning,provider)
    with TestClient(create_app(planning=planning,route_agent=fresh)) as client:
        recovered=client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'})
        assert recovered.status_code==200,recovered.text
        assert client.post(url,json=body).json()==recovered.json()
        assert client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).json()==recovered.json()
        state=client.get(url+'/attempts/'+body['request_id']).json()
        assert (state['state'],state['attempt'],state['retry_allowed'])==('succeeded',2,False)
        assert len(client.get(url).json()['messages'])==1
    assert len(calls)==2 and provider.totals()['attempts']==2
    assert planning.store.get(previous.route_id).result==previous
    for path in (planning.store.root/'requests').rglob('*.json'):
        assert 'NEVER-STORE-CREDENTIAL' not in path.read_text()


def test_retry_version_prevents_delayed_duplicate_retries(tmp_path):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded'}})
    planning,agent,_,previous=setup(tmp_path,handler)
    body=dict(request_id='versioned-retry-0001',message='Why?')
    url='/api/v1/routes/'+previous.route_id+'/chat'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        assert client.post(url,json=body).status_code==503
        assert client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).status_code==503
        stale=client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'})
        assert stale.status_code==409 and stale.json()['error']['code']=='CHAT_RETRY_CONFLICT'
        assert client.get(url+'/attempts/'+body['request_id']).json()['attempt']==2
    assert len(calls)==2


def test_retry_after_is_honored_without_sleeping_or_calling_provider(tmp_path,monkeypatch):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded'}},headers={'retry-after':'30'}) if len(calls)==1 else answer()
    planning,agent,_,previous=setup(tmp_path,handler)
    body=dict(request_id='rate-delay-request-01',message='Why?')
    url='/api/v1/routes/'+previous.route_id+'/chat'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        assert client.post(url,json=body).status_code==503
        state=client.get(url+'/attempts/'+body['request_id']).json()
        assert not state['retry_allowed'] and 0 < state['retry_after_seconds'] <= 30
        assert client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).json()['error']['code']=='CHAT_RETRY_DELAY'
        assert len(calls)==1
        later=now()+timedelta(seconds=31)
        monkeypatch.setattr('app.coordinator.attempts.now',lambda:later)
        assert client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).status_code==200
    assert len(calls)==2


def test_timeout_and_legacy_claims_remain_unknown_not_running(tmp_path):
    calls=[]
    def handler(req):
        calls.append(1); raise httpx.ReadTimeout('private-timeout-value',request=req)
    planning,agent,_,previous=setup(tmp_path,handler)
    body=dict(request_id='unknown-timeout-0001',message='Why?')
    url='/api/v1/routes/'+previous.route_id+'/chat'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        assert client.post(url,json=body).status_code==503
        state=client.get(url+'/attempts/'+body['request_id']).json()
        assert state['state']=='unknown' and not state['retry_allowed']
        assert client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).json()['error']['code']=='CHAT_RETRY_UNSAFE'
        directory=planning.store.root/'chat'/previous.route_id; directory.mkdir(exist_ok=True,parents=True)
        legacy='legacy-claim-request-01'; (directory/(legacy+'.claim')).write_text('claimed')
        assert client.get(url+'/attempts/'+legacy).json()['state']=='unknown'
        assert client.post(url,json={**body,'request_id':legacy}).json()['error']['code']=='CHAT_OUTCOME_UNKNOWN'
    assert len(calls)==1


def test_concurrent_workers_replay_one_chat_and_report_running(tmp_path):
    started,release=Event(),Event();calls=[]
    def handler(req):
        calls.append(1); started.set(); assert release.wait(5); return answer()
    planning,agent,_,previous=setup(tmp_path,handler)
    body=ChatRequest(request_id='concurrent-chat-0001',message='Why?')
    first,second=RouteChat(agent),RouteChat(agent)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(first.send,previous.route_id,body)
        assert started.wait(5)
        try:
            assert second.status(previous.route_id,body.request_id).state=='running'
            with pytest.raises(ApiProblem) as error: second.send(previous.route_id,body)
            assert error.value.code=='CHAT_MESSAGE_IN_PROGRESS'
        finally: release.set()
        response=pending.result(timeout=5)
    assert second.send(previous.route_id,body)==response
    assert len(calls)==1


def test_worker_exit_releases_lock_but_never_reexecutes_abandoned_work(tmp_path):
    root=tmp_path/'attempts';root.mkdir()
    key='abandoned-worker-0001'
    code="""import os,sys
from pathlib import Path
from app.coordinator.attempts import AttemptStore,Record,now,save_json,payload_hash
root=Path(sys.argv[1]);key=sys.argv[2]
with AttemptStore(root,'chat').lock(root/(key+'.lock')) as acquired:
 assert acquired
 save_json(root/(key+'.json'),Record(payload_hash=payload_hash({'message':'Why?'}),state='running',attempt=1,updated_at=now()).model_dump(mode='json'))
 os._exit(0)
"""
    subprocess.run([sys.executable,'-c',code,str(root),key],check=True,timeout=10)
    store=AttemptStore(root,'chat')
    state=store.status(key,lambda data,expected:None)
    assert state.state=='unknown' and not state.retry_allowed
    with pytest.raises(ApiProblem) as error:
        store.execute(key,{'message':'Why?'},lambda:pytest.fail('Must not execute'),lambda data,expected:None,retry_attempt=1)
    assert error.value.code=='CHAT_RETRY_UNSAFE'


def test_plan_idempotency_survives_restart_and_checks_input(tmp_path):
    calls=[]
    def handler(req): calls.append(1); return httpx.Response(200,json=model_response(decision()))
    planning,agent,_,_=setup(tmp_path,handler)
    body=request_for(planning.grid).model_dump(mode='json'); key='idempotent-plan-0001'
    headers={'Idempotency-Key':key}
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.post('/api/v1/routes/plan',json=body,headers=headers)
        assert response.status_code==200,response.text
        assert client.post('/api/v1/routes/plan',json=body,headers=headers).json()==response.json()
        assert client.post('/api/v1/routes/plan',json={**body,'mode':'safest'},headers=headers).json()['error']['code']=='PLAN_REQUEST_CONFLICT'
        assert client.get('/api/v1/routes/requests/'+key).json()['state']=='succeeded'
        assert client.post('/api/v1/routes/plan',json=body,headers={'Idempotency-Key':'../../escape'}).status_code==422
        assert client.post('/api/v1/routes/plan',json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).status_code==400
    with TestClient(create_app(planning=planning,route_agent=RouteAgent(agent.settings,planning,agent.provider))) as client:
        assert client.post('/api/v1/routes/plan',json=body,headers=headers).json()==response.json()
    assert len(calls)==1


def test_plan_rejection_requires_explicit_retry_and_replays_success(tmp_path):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(429,json={'error':{'code':'insufficient_quota'}}) if len(calls)==1 else httpx.Response(200,json=model_response(decision()))
    planning,agent,_,_=setup(tmp_path,handler)
    body=request_for(planning.grid).model_dump(mode='json');key='rejected-plan-0001'
    headers={'Idempotency-Key':key}
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        assert client.post('/api/v1/routes/plan',json=body,headers=headers).status_code==503
        assert client.post('/api/v1/routes/plan',json=body,headers=headers).status_code==503
        assert client.get('/api/v1/routes/requests/'+key).json()['retry_allowed'] is True
        result=client.post('/api/v1/routes/plan',json=body,headers={**headers,'X-A-Stellar-Retry-Attempt':'1'})
        assert result.status_code==200,result.text
        assert client.post('/api/v1/routes/plan',json=body,headers=headers).json()==result.json()
    assert len(calls)==2


def test_legacy_completed_messages_keep_replay_and_conflict_semantics(tmp_path):
    calls=[]
    def handler(req): calls.append(1); return answer()
    planning,agent,_,previous=setup(tmp_path,handler)
    body=ChatRequest(request_id='legacy-success-0001',message='Why?')
    chat=RouteChat(agent)
    completed=chat.send(previous.route_id,body)
    # Simulate an older successful record with a permanent claim and no new state.
    chat._attempts(previous.route_id).paths(body.request_id)[0].unlink()
    (planning.store.root/'chat'/previous.route_id/(body.request_id+'.claim')).write_text('claimed')
    assert chat.status(previous.route_id,body.request_id).state=='succeeded'
    assert chat.send(previous.route_id,body)==completed
    with pytest.raises(ApiProblem) as error:
        chat.send(previous.route_id,body.model_copy(update={'message':'Changed text'}))
    assert error.value.code=='CHAT_REQUEST_CONFLICT' and len(calls)==1


def test_published_response_recovers_after_final_status_write_failure(tmp_path,monkeypatch):
    import app.coordinator.attempts as attempts
    calls=[]
    def handler(req): calls.append(1); return answer()
    planning,agent,_,previous=setup(tmp_path,handler)
    body=ChatRequest(request_id='interrupted-status-01',message='Why?')
    original=attempts.save_json
    def interrupted(path,data):
        if data.get('state')=='succeeded': raise OSError('synthetic-status-write-failure')
        original(path,data)
    monkeypatch.setattr(attempts,'save_json',interrupted)
    with pytest.raises(OSError): RouteChat(agent).send(previous.route_id,body)
    monkeypatch.setattr(attempts,'save_json',original)
    fresh=RouteChat(agent)
    assert fresh.status(previous.route_id,body.request_id).state=='succeeded'
    response=fresh.send(previous.route_id,body)
    assert response.message_id==body.request_id and len(calls)==1


def test_independent_process_lock_reports_running_then_unknown(tmp_path):
    root=tmp_path/'attempts';root.mkdir();key='active-other-worker-01'
    code="""import os,sys
from pathlib import Path
from app.coordinator.attempts import AttemptStore,Record,now,save_json,payload_hash
root=Path(sys.argv[1]);key=sys.argv[2]
with AttemptStore(root,'chat').lock(root/(key+'.lock')) as acquired:
 assert acquired
 save_json(root/(key+'.json'),Record(payload_hash=payload_hash({'message':'Why?'}),state='running',attempt=1,updated_at=now()).model_dump(mode='json'))
 print('READY',flush=True)
 sys.stdin.readline()
 os._exit(0)
"""
    worker=subprocess.Popen([sys.executable,'-c',code,str(root),key],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert worker.stdout.readline().strip()=='READY'
        store=AttemptStore(root,'chat')
        assert store.status(key,lambda data,expected:None).state=='running'
        with pytest.raises(ApiProblem) as error:
            store.execute(key,{'message':'Why?'},lambda:pytest.fail('Duplicate worker execution'),lambda data,expected:None)
        assert error.value.code=='CHAT_MESSAGE_IN_PROGRESS'
        worker.communicate('exit\n',timeout=5)
        assert store.status(key,lambda data,expected:None).state=='unknown'
    finally:
        if worker.poll() is None: worker.kill();worker.wait(timeout=5)


def test_unrelated_request_keys_are_not_blocked_by_an_active_model_call(tmp_path):
    entered,release=Event(),Event();calls=[]
    def handler(req):
        calls.append(1)
        message=json.loads(json.loads(req.content)['input'][1]['content'])['message']
        if message=='First question': entered.set();assert release.wait(5)
        return answer()
    planning,agent,_,previous=setup(tmp_path,handler)
    chat=RouteChat(agent)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(chat.send,previous.route_id,ChatRequest(request_id='independent-first-01',message='First question'))
        assert entered.wait(5)
        try:
            second=chat.send(previous.route_id,ChatRequest(request_id='independent-second-01',message='Second question'))
            assert second.user_message=='Second question'
        finally: release.set()
        pending.result(timeout=5)
    assert len(calls)==2


@pytest.mark.parametrize('corruption',['invalid_json','unpaired_metadata'])
def test_a_corrupt_saved_response_never_executes_the_model_again(tmp_path,corruption):
    calls=[]
    def handler(req): calls.append(1); return answer()
    planning,agent,_,previous=setup(tmp_path,handler)
    chat=RouteChat(agent);body=ChatRequest(request_id='corrupt-response-0001',message='Why?')
    chat.send(previous.route_id,body)
    path=planning.store.root/'chat'/previous.route_id/(body.request_id+'.json')
    if corruption=='invalid_json':
        path.write_text('{broken-json')
    else:
        data=json.loads(path.read_text());data['metadata']=planning.store.get(previous.route_id).metadata.model_dump(mode='json')
        path.write_text(json.dumps(data))
    with pytest.raises(ApiProblem) as error: chat.send(previous.route_id,body)
    assert error.value.code=='REQUEST_RECORD_INVALID' and len(calls)==1
