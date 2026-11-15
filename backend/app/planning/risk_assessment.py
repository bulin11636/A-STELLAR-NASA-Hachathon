"""Versioned P1 risk/confidence enrichment for the walking assessment record."""
from app.contracts.assessment import (
    ASSESSMENT_AGENT_IDS, EvidenceQuality, MissionProfile, RiskFactor,
)


_WEIGHTS = {
    'safest': ({'A1':.75,'A2':0,'A3':.25,'A4':0,'A5':0,'A6':0}, {'A1':.55,'A2':.10,'A3':.25,'A4':0,'A5':0,'A6':.10}),
    'fastest': ({'A1':.90,'A2':0,'A3':.10,'A4':0,'A5':0,'A6':0}, {'A1':.60,'A2':.10,'A3':.10,'A4':.05,'A5':0,'A6':.15}),
    'science_priority': ({'A1':.80,'A2':0,'A3':.20,'A4':0,'A5':0,'A6':0}, {'A1':.35,'A2':.10,'A3':.10,'A4':.30,'A5':0,'A6':.15}),
    'balanced': ({'A1':.85,'A2':0,'A3':.15,'A4':0,'A5':0,'A6':0}, {'A1':.45,'A2':.10,'A3':.20,'A4':.15,'A5':0,'A6':.10}),
}


def mission_profile(profile_id):
    try: risk,confidence=_WEIGHTS[profile_id]
    except KeyError as exc: raise ValueError('Unsupported mission profile.') from exc
    return MissionProfile(profile_id=profile_id,version=f'{profile_id}-v1',risk_weights=risk,confidence_weights=confidence)


def enrich_risk_assessment(assessment, profile_id, traces):
    """Attach only facts the current planner can ground.

    A1 has complete terrain validation but no calibrated normalized score. Other
    specialist traces are context until a route-applicable factor model exists.
    Thus confidence is useful immediately while risk remains null rather than
    implying that missing evidence is low risk.
    """
    profile=mission_profile(profile_id)
    full=EvidenceQuality(availability=1,route_coverage=1,temporal_applicability=1,validation_provenance=1)
    empty=EvidenceQuality(availability=0,route_coverage=0,temporal_applicability=0,validation_provenance=0)
    trace={item.agent_id:item for item in traces}
    factors=[RiskFactor(agent_id='A1',kind='context',status='contextual',evidence_quality=full,
                        evidence_ids=['route-grid','route-validation'],message='Terrain traversability gate passed; no calibrated normalized A1 risk model is configured.')]
    for agent_id in ('A2','A3','A4','A6'):
        item=trace.get(agent_id)
        state='contextual' if item and item.execution_state in {'succeeded','cached'} else 'unassessed'
        message=(f'{agent_id} output is contextual and is not integrated into route risk.' if state=='contextual'
                 else f'No route-applicable {agent_id} risk factor is available.')
        factors.append(RiskFactor(agent_id=agent_id,kind='context',status=state,evidence_quality=empty,message=message))
    factors.append(RiskFactor(agent_id='A5',kind='context',status='not_applicable',evidence_quality=empty,
                              message='A5 is not available as an independent factor for this mission profile.'))
    by_agent={factor.agent_id:factor for factor in factors}
    confidence=sum(profile.confidence_weights[agent]*by_agent[agent].evidence_quality.score for agent in ASSESSMENT_AGENT_IDS)
    return assessment.model_copy(update={
        'mission_profile':profile,
        'hard_gate_status':'pass',
        'risk_score':None,
        'assessment_confidence':confidence,
        'risk_factors':factors,
        'limitations':[ *assessment.limitations, 'Risk score is not assessed because no calibrated normalized route-risk factors are configured.'],
    })
