"""Auditable relative engineering assessment; no astronaut safety inference."""
import math
from datetime import datetime, timezone

from app.contracts.assessment import ASSESSMENT_AGENT_IDS, EvidenceDescription, EvidenceQuality, RiskFactor, RouteAssessment
from app.planning.policies import FORMULA_VERSION, mission_profile, selected_profile

ZERO=EvidenceQuality(availability=0,route_coverage=0,temporal_applicability=0,validation_provenance=0)


def fuse(assessment,profile,factors):
    """Gate first, then rank only a complete set of applicable risk factors."""
    if len(factors)!=6 or {f.agent_id for f in factors}!=set(ASSESSMENT_AGENT_IDS):
        raise ValueError('Assessment requires exactly one explicit entry for A1-A6.')
    by_id={f.agent_id:f for f in factors}
    blocked=assessment.hard_gate_status=='blocked' or bool(assessment.required_failed) or assessment.radiation_constraint_status=='fail'
    missing=[a for a,w in profile.risk_weights.items() if w>0 and (by_id[a].status!='assessed' or by_id[a].risk_score is None)]
    gate='blocked' if blocked else 'unassessed' if missing or assessment.required_unassessed else 'pass'
    reasons=[]
    if blocked: reasons.append('A required scenario budget was exceeded; this is not a mission-feasible route.')
    if missing: reasons.append('Comparable risk requires applicable factors: '+', '.join(missing)+'.')
    if assessment.required_unassessed: reasons.append('User-required analyses remain unassessed: '+', '.join(assessment.required_unassessed)+'.')
    denominator=sum(w for a,w in profile.confidence_weights.items() if by_id[a].status!='not_applicable')
    enriched=[]
    for factor in factors:
        usable=factor.status in ('assessed','contextual')
        confidence=100*profile.confidence_weights[factor.agent_id]*factor.evidence_quality.score/denominator if usable and denominator else 0
        risk=100*profile.risk_weights[factor.agent_id]*factor.risk_score if factor.risk_score is not None else None
        enriched.append(factor.model_copy(update={'confidence_contribution':confidence,'risk_contribution':risk}))
    confidence=sum(f.confidence_contribution for f in enriched)
    risk=sum(f.risk_contribution or 0 for f in enriched) if gate=='pass' else None
    result=assessment.model_copy(update=dict(schema_version='2',formula_version=FORMULA_VERSION,score_scale='0..100',
        mission_profile=profile,hard_gate_status=gate,gate_reasons=reasons,risk_score=risk,
        assessment_confidence=min(100.0,confidence),risk_factors=enriched))
    if confidence<70:
        missing_context=[f.agent_id for f in enriched if f.status not in ('assessed','contextual','not_applicable')]
        message='Assessment confidence is below 70/100; inspect missing factors, route coverage, acquisition time and provenance before comparison.'
        if missing_context: message+=' Missing or unassessed: '+', '.join(missing_context)+'.'
        result=result.model_copy(update={'limitations':[*result.limitations,message]})
    return RouteAssessment.model_validate(result.model_dump())


def terrain_factor(grid,touched,evidence_ids,*,now=None):
    """Peak conservative slope utilization, relative to the host demo threshold."""
    if grid is None or not touched:
        return RiskFactor(agent_id='A1',kind='risk',status='unassessed',evidence_quality=ZERO,
            message='No independently checked terrain cells were supplied.')
    timestamp=grid.profile.acquisition_time
    temporal=0.0;state='assessed';reason='Acquisition time is unknown; no present-day terrain freshness is inferred.'
    if timestamp:
        try:
            acquired=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
            if acquired.utcoffset() is None: raise ValueError('Timezone required')
            age=((now or datetime.now(timezone.utc))-acquired).total_seconds()/86400
            # An explicitly documented engineering horizon, not a NASA hazard limit.
            if age<0: state='incompatible';reason='Acquisition time is in the future.'
            elif age>3650: state='stale';reason='Terrain source exceeds the 3,650-day engineering applicability horizon.'
            else: temporal=1.0;reason='Acquisition falls within the declared 3,650-day engineering horizon.'
        except ValueError:
            state='incompatible';reason='Acquisition time is invalid or lacks a time zone.'
    peak=max(float(grid.slope[r,c]) for r,c in touched)
    if not math.isfinite(peak) or peak>grid.profile.slope_threshold_deg+1e-8:
        raise ValueError('Terrain factor includes unknown or blocked slope.')
    score=min(1.0,(peak/grid.profile.slope_threshold_deg)**2) if state=='assessed' else None
    quality=EvidenceQuality(availability=1,route_coverage=1,temporal_applicability=temporal,validation_provenance=.5)
    return RiskFactor(agent_id='A1',kind='risk',status=state,risk_score=score,evidence_quality=quality,evidence_ids=evidence_ids,
        model_version='conservative-peak-slope-utilization-v1',evidence=EvidenceDescription(
            dataset_ids=[grid.profile.dataset_id],source_urls=[grid.profile.source_url] if grid.profile.source_url else [],
            dataset_version=grid.source_hash,acquisition_time=timestamp,route_coverage_fraction=1.0,
            uncertainty='Host-asserted elevation units and conservative aggregation; no optical or physiological model.'),component_reasons={
            'availability':'Versioned DEM data were read and source integrity checked.',
            'route_coverage':'All closed-cell route intersections passed terrain validation; aggregated cells are conservative.',
            'temporal_applicability':reason,
            'validation_provenance':'Source hash and geometry verified; elevation units remain host-asserted, not publisher-certified.'},
        message='Relative peak slope utilization against a configurable engineering threshold; excludes optical obstacles and physiological safety.')


def radiation_factor(assessment,trace,evidence_id):
    usable=trace and trace.application=='dose_scenario' and trace.execution_state in ('succeeded','cached')
    if not usable:
        return RiskFactor(agent_id='A3',kind='risk',status='unavailable',evidence_quality=ZERO,
            message='An applicable, source-identified radiation scenario is missing; no dose risk is inferred.')
    quality=EvidenceQuality(availability=1,route_coverage=1,temporal_applicability=1,validation_provenance=.5)
    score=None;status='unassessed'
    # Budget is supplied separately in enrich_risk_assessment; never invent one.
    return RiskFactor(agent_id='A3',kind='risk',status=status,evidence_quality=quality,evidence_ids=[evidence_id],
        model_version='upper-scenario-budget-utilization-v1',component_reasons={
            'availability':'Configured scenario output is source-identified.',
            'route_coverage':'Constant-rate mission scenario covers the explicitly supplied route duration; no spatial hazard map.',
            'temporal_applicability':'Duration lies within the explicit hypothetical scenario scope; this is not current radiation telemetry.',
            'validation_provenance':'Unit arithmetic and scenario provenance checked; transfer to Jezero is hypothetical.'},
        message='Scenario dose requires an explicit budget and a bounded uncertainty band before relative comparison.')


def enrich_risk_assessment(assessment, profile_id, traces, *, grid=None,touched=(),route_id=None,request=None,evidence_descriptions=None,evidence_applicability=None):
    profile=mission_profile(profile_id)
    refs=lambda agent: route_id+':provenance#'+agent if route_id else 'synthetic:'+agent
    by_id={t.agent_id:t for t in traces}
    terrain=terrain_factor(grid,touched,[route_id+':grid',route_id+':validation'] if route_id else [])
    radiation=radiation_factor(assessment,by_id.get('A3'),refs('A3'))
    budget=request.mission.radiation_budget_usv if request and request.mission else None
    if radiation.evidence_ids and assessment.dose_estimate_usv is not None and assessment.dose_uncertainty_usv is not None and budget is not None:
        upper=assessment.dose_estimate_usv+assessment.dose_uncertainty_usv
        score=(0.0 if upper==0 else 1.0) if budget==0 else min(1.0,upper/budget)
        if assessment.radiation_constraint_status in ('pass','fail'):
            radiation=radiation.model_copy(update={'status':'assessed','risk_score':score,
                'message':'Relative upper-band scenario dose divided by the user budget; a scenario comparison, not astronaut safety.'})
    factors=[terrain,radiation]
    for agent in ('A2','A4','A6'):
        trace=by_id.get(agent)
        usable=trace and trace.application=='context_only' and trace.execution_state in ('succeeded','cached')
        status='contextual' if usable and agent in ('A4','A6') else 'unassessed' if trace and trace.selected else 'unavailable'
        quality=EvidenceQuality(availability=1,route_coverage=0,temporal_applicability=0,validation_provenance=1) if usable else ZERO
        factors.append(RiskFactor(agent_id=agent,kind='context',status=status,evidence_quality=quality,
            evidence_ids=[refs(agent)] if usable else [],component_reasons={
                'route_coverage':'No validated route-risk coverage model is configured.',
                'temporal_applicability':'Context timestamps do not establish mission-time hazard applicability.'},
            message='Source-grounded context only; no calibrated route-risk model.' if usable else 'Applicable specialist evidence is unavailable or unassessed.'))
    factors.append(RiskFactor(agent_id='A5',kind='context',status='not_applicable',evidence_quality=ZERO,
        message='Surface obstacle responsibility belongs to the terrain specialist; no independent validated optical factor. Its profile weights are explicitly zero.'))
    for i,factor in enumerate(factors):
        if (evidence_applicability or {}).get(factor.agent_id)=='incompatible':
            factor=factor.model_copy(update={'status':'incompatible','risk_score':None,'evidence_quality':ZERO,
                'message':'Configured specialist inputs do not match the declared region, ROI or dataset version.'})
            factors[i]=factor
        description=(evidence_descriptions or {}).get(factor.agent_id)
        if description is not None: factors[i]=factor.model_copy(update={'evidence':EvidenceDescription.model_validate(description)})
    result=fuse(assessment,profile,sorted(factors,key=lambda f:f.agent_id))
    return result.model_copy(update={'limitations':[*result.limitations,
        'Relative engineering terrain/scenario scores do not certify astronaut safety.',
        'Science and rover context do not reduce terrain cost or supply safety scores.']})
