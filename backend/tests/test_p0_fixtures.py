"""Shared fixtures validate against backend contracts and retain coherent pairs."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.contracts.attempts import RequestAttemptStatus
from app.contracts.chat import ChatRequest, ChatResponse
from app.contracts.routes import StoredRouteResponse

ROOT=Path(__file__).resolve().parents[2]
FIXTURES=ROOT/'data/fixtures/p0'
STATUS_NAMES=['plan-running','plan-succeeded','plan-failed-retryable','plan-failed-non-retryable',
    'plan-unknown','chat-failed-retryable','chat-succeeded-revision.status']


@pytest.mark.parametrize('name',STATUS_NAMES)
def test_shared_status_fields_nullability_and_retry_rules(name):
    data=json.loads((FIXTURES/(name+'.json')).read_text())
    assert set(data)=={'request_id','state','attempt','retry_allowed','retry_after_seconds','error','updated_at'}
    status=RequestAttemptStatus.model_validate(data)
    if status.state in ('running','succeeded'):
        assert status.error is None
    else:
        assert set(data['error'])=={'code','message','details'}
        if name=='plan-failed-non-retryable':
            assert data['error']['details'][0]['hard_gate_status']=='blocked'
        else: assert data['error']['details'] is None
    assert not status.retry_allowed or (status.state=='failed' and status.retry_after_seconds==0)
    if status.state=='unknown': assert status.retry_allowed is False


def test_shared_revision_matches_parent_context_and_result():
    parent=StoredRouteResponse.model_validate_json((FIXTURES/'parent-route.json').read_text())
    request=ChatRequest.model_validate_json((FIXTURES/'chat-succeeded-revision.request.json').read_text())
    response=ChatResponse.model_validate_json((FIXTURES/'chat-succeeded-revision.json').read_text())
    request.advanced_context.require_parent(parent.metadata.request)
    assert response.route_id==parent.result.route_id==response.metadata.parent_route_id
    assert response.result.route_id!=parent.result.route_id
    assert response.result.mode==response.metadata.request.mode=='safest'
    assert parent.result.mode=='shortest'
    assert response.result.route[0]==parent.result.route[0]
    assert response.result.route[-1]==parent.result.route[-1]
    assert response.message_id==request.request_id


def test_fixture_generator_exercises_real_api_with_no_live_configuration(tmp_path):
    spec=importlib.util.spec_from_file_location('export_p0_fixtures',ROOT/'scripts/export_p0_fixtures.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    try:
        files=module.export(tmp_path)
    finally:
        sys.path.remove(str(ROOT/'scripts'))
    assert set(files)=={p.name for p in FIXTURES.glob('*.json')}
    for name in STATUS_NAMES:
        expected=RequestAttemptStatus.model_validate_json((FIXTURES/(name+'.json')).read_text())
        actual=RequestAttemptStatus.model_validate_json((tmp_path/(name+'.json')).read_text())
        assert actual==expected
