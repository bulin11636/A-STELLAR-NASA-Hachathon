import pytest
from pydantic import ValidationError

from app.contracts.assessment import EvidenceQuality, MissionProfile, RiskFactor
from app.planning.assessment import walking_assessment
from app.planning.risk_assessment import enrich_risk_assessment, mission_profile


def test_terrain_only_assessment_keeps_risk_unknown_and_reports_coverage():
    assessment=enrich_risk_assessment(walking_assessment(type('Request',(),{'mission':None})(),100), 'balanced', [])
    assert assessment.hard_gate_status == 'pass'
    assert assessment.risk_score is None
    assert assessment.assessment_confidence == pytest.approx(.45)
    assert next(factor for factor in assessment.risk_factors if factor.agent_id == 'A5').status == 'not_applicable'


def test_profile_and_factor_contract_reject_implicit_gaps_and_unknown_quality():
    with pytest.raises(ValidationError):
        MissionProfile(profile_id='balanced',version='balanced-v1',risk_weights={'A1':1},confidence_weights={'A1':1})
    with pytest.raises(ValidationError):
        RiskFactor(agent_id='A3',kind='context',status='unassessed',
            evidence_quality=EvidenceQuality(availability=.1,route_coverage=0,temporal_applicability=0,validation_provenance=0),message='Missing.')
    assert mission_profile('safest').version == 'safest-v1'
