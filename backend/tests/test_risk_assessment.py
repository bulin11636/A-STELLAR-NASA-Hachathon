import pytest
from pydantic import ValidationError

from app.contracts.assessment import EvidenceQuality, MissionProfile, RiskFactor, RouteAssessment
from app.planning.assessment import walking_assessment
from app.planning.risk_assessment import enrich_risk_assessment, mission_profile, fuse


def test_terrain_only_assessment_keeps_risk_unknown_and_reports_coverage():
    assessment=enrich_risk_assessment(walking_assessment(type('Request',(),{'mission':None})(),100), 'balanced', [])
    assert assessment.hard_gate_status == 'unassessed'
    assert assessment.risk_score is None
    assert assessment.assessment_confidence == 0
    assert next(factor for factor in assessment.risk_factors if factor.agent_id == 'A5').status == 'not_applicable'


def test_profile_and_factor_contract_reject_implicit_gaps_and_unknown_quality():
    with pytest.raises(ValidationError):
        MissionProfile(profile_id='balanced',version='balanced-v1',risk_weights={'A1':1},confidence_weights={'A1':1})
    with pytest.raises(ValidationError):
        RiskFactor(agent_id='A3',kind='context',status='unassessed',
            evidence_quality=EvidenceQuality(availability=.1,route_coverage=0,temporal_applicability=0,validation_provenance=0),message='Missing.')
    assert mission_profile('safest').version == 'safest-v2'


def factors(terrain=.4,radiation=None):
    quality=EvidenceQuality(availability=1,route_coverage=1,temporal_applicability=1,validation_provenance=1)
    zero=EvidenceQuality(availability=0,route_coverage=0,temporal_applicability=0,validation_provenance=0)
    result=[]
    for agent in ('A1','A2','A3','A4','A5','A6'):
        score=terrain if agent=='A1' else radiation if agent=='A3' else None
        result.append(RiskFactor(agent_id=agent,kind='risk' if agent in ('A1','A3') else 'context',
            status='assessed' if score is not None else 'not_applicable' if agent=='A5' else 'unavailable',risk_score=score,
            evidence_quality=quality if score is not None else zero,evidence_ids=['synthetic:'+agent] if score is not None else [],message='Synthetic test factor.'))
    return result


@pytest.mark.parametrize('profile,coverage',[('safest',75),('fastest',90),('balanced',85),('science_priority',80)])
def test_partial_risk_normalizes_available_weights_without_zero_filling(profile,coverage):
    assessment=fuse(RouteAssessment(),mission_profile(profile),factors())
    assert assessment.risk_score is None and assessment.hard_gate_status=='unassessed'
    assert assessment.partial_risk_score==pytest.approx(40)
    assert assessment.risk_evidence_coverage==coverage
    legacy=assessment.model_dump();legacy.pop('partial_risk_score');legacy.pop('risk_evidence_coverage')
    assert RouteAssessment.model_validate(legacy).partial_risk_score==pytest.approx(40)
    legacy['partial_risk_score']=4.0
    with pytest.raises(ValidationError):RouteAssessment.model_validate(legacy)


def test_full_zero_missing_and_blocked_scores_remain_distinct():
    p=mission_profile('safest')
    complete=fuse(RouteAssessment(),p,factors(.4,.8))
    assert complete.risk_score==pytest.approx(50)
    assert complete.partial_risk_score==pytest.approx(50) and complete.risk_evidence_coverage==100
    missing=fuse(RouteAssessment(),p,factors(None,None))
    assert missing.partial_risk_score is None and missing.risk_evidence_coverage==0
    zero=fuse(RouteAssessment(),p,factors(0,None))
    assert zero.partial_risk_score==0 and zero.risk_score is None
    blocked=fuse(RouteAssessment(required_failed=['A3']),p,factors(.4,.8))
    assert blocked.hard_gate_status=='blocked' and blocked.risk_score is None
    assert blocked.partial_risk_score==pytest.approx(50)


def test_legacy_immutable_route_audit_upgrades_derived_fields_without_rewriting(tmp_path):
    import json
    from app.planning.service import PlanningService
    from app.planning.grid import digest
    from test_planning import fixture_profile,request_for
    planning=PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    result=planning.plan(request_for(planning.grid).model_copy(update={'mission_profile':'fastest'}))
    folder=planning.store.root/result.route_id
    record=json.loads((folder/'record.json').read_text())
    audit=json.loads((folder/'provenance.json').read_text())
    for value in (record['metadata']['assessment'],audit['assessment']):
        value.pop('partial_risk_score');value.pop('risk_evidence_coverage')
    (folder/'provenance.json').write_text(json.dumps(audit))
    record['metadata']['artifacts']['provenance']['sha256']=digest(folder/'provenance.json')
    (folder/'record.json').write_text(json.dumps(record))
    manifest=json.loads((folder/'complete.json').read_text())
    manifest.update({name:digest(folder/name) for name in ('record.json','provenance.json')})
    (folder/'complete.json').write_text(json.dumps(manifest))
    before={name:digest(folder/name) for name in (*manifest,'complete.json')}
    restored=planning.store.get(result.route_id)
    assert restored.metadata.assessment.partial_risk_score==0
    assert restored.metadata.assessment.risk_evidence_coverage==90
    assert {name:digest(folder/name) for name in before}==before
