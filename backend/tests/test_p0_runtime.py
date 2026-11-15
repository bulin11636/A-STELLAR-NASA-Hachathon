"""Dataset, storage, credentials and historic transport state stay distinct."""
import sqlite3

from fastapi.testclient import TestClient
import httpx
import pytest

from app.main import create_app
from app.planning.service import PlanningService
from test_planning import fixture_profile
from test_request_recovery import setup
from test_route_agent import decision, model_response


def test_readiness_storage_failure_is_separate_from_dataset_and_credential(tmp_path,monkeypatch):
    def handler(req): pytest.fail('Runtime checks cannot call the provider')
    planning,agent,_,_=setup(tmp_path,handler)
    def unavailable(*a,**kw): raise PermissionError('private-path-and-key')
    monkeypatch.setattr('app.runtime.tempfile.TemporaryFile',unavailable)
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        ready=client.get('/api/v1/ready')
        assert ready.status_code==503
        assert ready.json()['checks']==dict(planning=True,storage=False,model_credentials=True)
        assert ready.json()['provider_access_verified'] is False
        assert client.get('/api/v1/health').status_code==200
        status=client.get('/api/v1/a0/status')
        assert status.status_code==200
        assert status.json()['checks']['storage'] is False
        assert status.json()['usage_available'] is False
        assert status.json()['configured'] is True
        assert 'private-path' not in ready.text+status.text
        assert str(tmp_path) not in ready.text+status.text


def test_status_separates_configuration_from_provider_observation_without_calls(tmp_path):
    calls=[]
    def handler(req): calls.append(1); return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded','message':'private-provider-text'}})
    planning,agent,provider,previous=setup(tmp_path,handler)
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        status=client.get('/api/v1/a0/status').json()
        assert status['provider']==dict(availability='not_checked',last_request_outcome='not_requested',last_http_status=None)
        assert status['configured'] and not status['provider_access_verified'] and status['usage_available']
        assert client.get('/api/v1/ready').status_code==200
        assert calls==[]
        assert client.post('/api/v1/routes/'+previous.route_id+'/chat',json=dict(message='Explain.',request_id='status-provider-0001')).status_code==503
        result=client.get('/api/v1/a0/status')
        assert result.json()['provider']==dict(availability='not_checked',last_request_outcome='rejected',last_http_status=429)
        assert result.json()['last_provider_error']['http_status']==429
        assert result.json()['budget']['attempts']==1
        assert 'private-provider-text' not in result.text
        assert len(calls)==1


def test_success_observation_does_not_claim_current_provider_access(tmp_path):
    planning,agent,_,previous=setup(tmp_path,lambda req:httpx.Response(200,json=model_response(decision('answer'))))
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        assert client.post('/api/v1/routes/'+previous.route_id+'/chat',json=dict(message='Explain.',request_id='success-provider-001')).status_code==200
        status=client.get('/api/v1/a0/status').json()
        assert status['provider']['last_request_outcome']=='response_received'
        assert status['provider']['availability']=='not_checked' and not status['provider_access_verified']


def test_corrupt_usage_ledger_is_reported_without_private_exception(tmp_path):
    planning,agent,provider,_=setup(tmp_path,lambda req:pytest.fail('No provider request'))
    provider.path.parent.mkdir(parents=True,exist_ok=True)
    provider.path.write_text('private-corrupt-ledger')
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.get('/api/v1/a0/status')
        assert response.status_code==200
        assert response.json()['checks']['storage'] is False
        assert response.json()['budget'] is None and not response.json()['usage_available']
        assert 'private-corrupt-ledger' not in response.text
        assert client.get('/api/v1/ready').status_code==503


def test_deterministic_status_has_explicit_disabled_provider(tmp_path):
    planning=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    with TestClient(create_app(planning=planning)) as client:
        ready=client.get('/api/v1/ready')
        assert ready.status_code==200
        assert ready.json()['checks']==dict(planning=True,storage=True,model_credentials=True)
        status=client.get('/api/v1/a0/status').json()
        assert status['mode']=='deterministic' and status['provider']['availability']=='disabled'
        assert status['last_provider_error'] is None and not status['usage_available']


def test_unexpected_failure_logs_type_without_exception_secrets(caplog,tmp_path):
    class Broken:
        async def plan_mock_route(self,body):
            raise RuntimeError('sk-private-credential /private/runtime.env')
    planning=PlanningService(output_root=tmp_path/'routes')
    with TestClient(create_app(Broken(),planning=planning),raise_server_exceptions=False) as client:
        response=client.post('/api/v1/routes/plan',json=dict(region_id='jezero',coordinate_system='MARS_2000_PLANETOCENTRIC_EAST_360_V1',
            start=dict(longitude=77,latitude=18),goal=dict(longitude=78,latitude=19),mode='shortest'))
        assert response.status_code==500 and response.json()['error']['code']=='INTERNAL_ERROR'
        assert 'RuntimeError' in caplog.text
        assert 'sk-private' not in caplog.text+response.text and '/private/runtime.env' not in caplog.text+response.text


def test_request_lock_storage_failure_returns_safe_envelope_without_generation(tmp_path,monkeypatch):
    planning,agent,_,previous=setup(tmp_path,lambda req:pytest.fail('No provider call'))
    def fail(*a,**kw): raise sqlite3.OperationalError('private-storage-path')
    monkeypatch.setattr('app.coordinator.attempts.sqlite3.connect',fail)
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.post('/api/v1/routes/'+previous.route_id+'/chat',json=dict(message='Explain.',request_id='storage-failure-0001'))
        assert response.status_code==503
        assert response.json()['error']['code']=='REQUEST_STORAGE_UNAVAILABLE'
        assert 'private-storage-path' not in response.text


def test_failed_local_reservation_is_retryable_and_never_reaches_provider(tmp_path):
    planning,agent,provider,previous=setup(tmp_path,lambda req:pytest.fail('No provider request'))
    provider.path.parent.mkdir(parents=True,exist_ok=True)
    provider.path.write_text('private-invalid-ledger')
    url='/api/v1/routes/'+previous.route_id+'/chat'
    with TestClient(create_app(planning=planning,route_agent=agent)) as client:
        response=client.post(url,json=dict(message='Explain.',request_id='local-reservation-001'))
        assert response.status_code==503 and response.json()['error']['code']=='A0_STORAGE_UNAVAILABLE'
        status=client.get(url+'/attempts/local-reservation-001').json()
        assert status['state']=='failed' and status['retry_allowed']
        assert 'private-invalid-ledger' not in response.text


def test_unexpected_chat_failure_is_internal_error_with_durable_unknown_state(tmp_path,monkeypatch,caplog):
    planning,agent,_,previous=setup(tmp_path,lambda req:pytest.fail('No provider request'))
    calls=[]
    def broken(*a,**kw):
        calls.append(1)
        raise RuntimeError('sk-private-runtime /private/runtime.env')
    monkeypatch.setattr(agent,'respond',broken)
    url='/api/v1/routes/'+previous.route_id+'/chat'
    body=dict(message='Explain.',request_id='internal-failure-0001')
    with TestClient(create_app(planning=planning,route_agent=agent),raise_server_exceptions=False) as client:
        failed=client.post(url,json=body)
        assert failed.status_code==500 and failed.json()['error']['code']=='INTERNAL_ERROR'
        state=client.get(url+'/attempts/'+body['request_id']).json()
        assert state['state']=='unknown' and not state['retry_allowed']
        assert client.post(url,json=body).json()==failed.json()
        assert client.post(url,json=body,headers={'X-A-Stellar-Retry-Attempt':'1'}).status_code==409
    assert calls==[1] and 'RuntimeError' in caplog.text
    assert 'sk-private' not in caplog.text+failed.text and '/private/runtime.env' not in caplog.text+failed.text
