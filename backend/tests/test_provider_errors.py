"""429 diagnostics preserve actionable codes, not credentials or response text."""
import json
import sqlite3

import httpx
import pytest

from app.api.errors import ApiProblem
from app.coordinator.metered import MeteredProvider
from app.coordinator.provider_errors import describe_429
from app.coordinator.settings import AgentSettings


@pytest.mark.parametrize('code,expected',[
    ('credit_balance_exhausted','A0_CREDIT_BALANCE_EXHAUSTED'),
    ('organization_usage_limit_exceeded','A0_API_USAGE_LIMIT'),
    ('organization_spend_limit_exceeded','A0_API_SPEND_LIMIT'),
    ('project_spend_limit_exceeded','A0_API_SPEND_LIMIT'),
    ('insufficient_quota','A0_QUOTA_EXHAUSTED'),
    ('rate_limit_exceeded','A0_RATE_LIMITED'),
    ('slow_down','A0_RATE_LIMITED'),
])
def test_specific_codes_persist_across_restart_without_retry(tmp_path,code,expected):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(429,json={'error':{'code':code,'type':'insufficient_quota','message':'private-provider-text'}},
            headers={'x-request-id':'req_fixture_01','retry-after':'30'})
    settings=AgentSettings(enabled=True,api_key='synthetic-test-key')
    provider=MeteredProvider(settings,tmp_path,httpx.MockTransport(handler))
    with pytest.raises(ApiProblem) as failure:
        provider.decide({'evidence':[]},'Explain this route.')
    assert failure.value.code==expected
    assert 'private-provider-text' not in failure.value.message
    diagnostic=MeteredProvider(settings,tmp_path).last_failure()
    assert diagnostic['error_code']==code
    assert diagnostic['public_code']==expected
    assert diagnostic['request_id']=='req_fixture_01' and diagnostic['retry_after_seconds']==30
    assert 'private-provider-text' not in json.dumps(diagnostic)
    assert len(calls)==1 and provider.totals()['attempts']==1


@pytest.mark.parametrize('body',[None,[],{'error':None},{'error':{'code':['invalid']}},
    {'error':{'code':'private-secret','type':'private-secret','message':'private-secret'}}])
def test_unknown_or_malformed_errors_remain_ambiguous_and_safe(body):
    diagnostic,message=describe_429(body,{'retry-after':'NaN','x-request-id':'private-secret'})
    assert diagnostic['public_code']=='A0_RATE_OR_QUOTA_LIMIT'
    assert diagnostic['error_code'] is None and diagnostic['error_type'] is None
    assert diagnostic['retry_after_seconds'] is None and diagnostic['request_id'] is None
    assert 'private-secret' not in json.dumps(diagnostic)+message


def test_broad_type_without_specific_code_and_old_ledger(tmp_path):
    diagnostic,_=describe_429({'error':{'type':'insufficient_quota'}},{})
    assert diagnostic['public_code']=='A0_QUOTA_EXHAUSTED'
    provider=MeteredProvider(AgentSettings(),tmp_path)
    assert provider.last_failure() is None
    assert not provider.path.exists()
    with sqlite3.connect(provider.path) as db:
        db.execute('CREATE TABLE calls (id TEXT PRIMARY KEY, status TEXT, reserved REAL, actual REAL, usage TEXT)')
        db.execute("INSERT INTO calls VALUES ('old','http_429',0,NULL,NULL)")
    assert provider.last_failure() is None


def test_diagnostic_command_never_generates_or_changes_the_ledger(tmp_path):
    import importlib.util
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('diagnose_a0',root/'scripts/diagnose_a0.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    settings=AgentSettings(enabled=True,api_key='synthetic-private-key',usage_root=tmp_path)
    seen=[]
    def handler(request):
        seen.append((request.method,str(request.url)))
        assert request.headers['authorization']=='Bearer synthetic-private-key'
        return httpx.Response(200,json={'data':[{'id':settings.model}]})
    report=module.diagnose(settings,check_access=True,transport=httpx.MockTransport(handler))
    assert seen==[('GET','https://api.openai.com/v1/models')]
    assert report['access_check']['configured_model_listed'] is True
    assert report['generation_requests']==0
    assert 'synthetic-private-key' not in json.dumps(report)
    assert not (tmp_path/'a0-usage.sqlite3').exists()
    assert module.diagnose(settings)['last_provider_error'] is None


@pytest.mark.parametrize('failure,stage',[
    ('incomplete','output_limit'),('refusal','tool_call'),
    ('bad_arguments','arguments'),('bad_citation','evidence_citations'),('missing_usage','usage'),
])
def test_proposal_diagnostics_identify_failure_without_retaining_private_output(tmp_path,failure,stage):
    proposal=dict(action='answer',message='private-response-text',mode=None,waypoints=None,citations=['A1'])
    body=dict(status='completed',output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
        usage=dict(input_tokens=500,output_tokens=100))
    if failure=='incomplete':
        body.update(status='incomplete',incomplete_details={'reason':'max_output_tokens'})
    elif failure=='refusal': body['output']=[]
    elif failure=='bad_arguments': body['output'][0]['arguments']='{"private-secret":"bad"}'
    elif failure=='bad_citation':
        proposal['citations']=['private-secret']
        body['output'][0]['arguments']=json.dumps(proposal)
    elif failure=='missing_usage': del body['usage']
    requests=[]
    def handler(request):
        requests.append(1)
        return httpx.Response(200,json=body)
    settings=AgentSettings(enabled=True,api_key='private-api-key')
    provider=MeteredProvider(settings,tmp_path,httpx.MockTransport(handler))
    with pytest.raises(ApiProblem) as error:
        provider.decide({'evidence':[dict(id='A1',status='ready',kind='observed')]},'private-user-text')
    assert error.value.details==[{'stage':stage,'operation':'propose_route_action'}]
    assert error.value.outcome_unknown==(failure=='missing_usage')
    diagnostic=MeteredProvider(settings,tmp_path).last_failure()
    assert diagnostic['error_code']==stage
    assert 'private-' not in json.dumps(diagnostic)+error.value.message
    assert len(requests)==1 and provider.totals()['attempts']==1


@pytest.mark.parametrize('available',[True,False])
def test_citation_schema_prevents_unavailable_evidence_choices(tmp_path,available):
    def handler(request):
        payload=json.loads(request.content)
        citations=payload['tools'][0]['parameters']['properties']['citations']
        if available: assert citations['items']['enum']==['A1']
        else: assert citations['maxItems']==0
        proposal=dict(action='answer',message='Terrain context.',mode=None,waypoints=None,citations=['A1'] if available else [])
        return httpx.Response(200,json=dict(status='completed',
            output=[dict(type='function_call',name='propose_route_action',arguments=json.dumps(proposal))],
            usage=dict(input_tokens=500,output_tokens=100)))
    provider=MeteredProvider(AgentSettings(enabled=True,api_key='test'),tmp_path,httpx.MockTransport(handler))
    result,_=provider.decide({'evidence':[dict(id='A1',status='ready' if available else 'unavailable',kind='observed'),
        dict(id='A6',status='failed',kind='observed')]},'Explain')
    assert result.citations==(['A1'] if available else [])


def test_local_request_limit_is_distinct_from_cost_and_recovers_without_clearing_history(tmp_path):
    settings=AgentSettings(enabled=True,api_key='test',max_calls=1,budget_usd=2)
    provider=MeteredProvider(settings,tmp_path)
    provider._reserve()
    with pytest.raises(ApiProblem) as error: provider._reserve()
    assert error.value.code=='A0_BUDGET_EXHAUSTED'
    assert 'request limit' in error.value.message and '1/1' in error.value.message
    assert error.value.retry_safe
    settings.max_calls=200
    provider._reserve()
    assert provider.totals()['attempts']==2
    settings.budget_usd=.01
    with pytest.raises(ApiProblem) as error: provider._reserve()
    assert 'cost budget' in error.value.message
