"""Walking assumptions and auditable specialist decisions; no safety defaults."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.contracts.base import ContractModel

OptionalAgent = Literal['A2','A3','A4','A6']
AssessmentAgentId = Literal['A1','A2','A3','A4','A5','A6']
MissionProfileId = Literal['safest','fastest','science_priority','balanced']
UnitScore = Annotated[float, Field(strict=True,ge=0,le=1,allow_inf_nan=False)]
PercentScore = Annotated[float, Field(strict=True,ge=0,le=100,allow_inf_nan=False)]
ASSESSMENT_AGENT_IDS: tuple[AssessmentAgentId,...] = ('A1','A2','A3','A4','A5','A6')


class WalkingMission(ContractModel):
    mode: Literal['walking'] = 'walking'
    speed_m_s: float | None = Field(default=None, gt=0, le=20, strict=True)
    stop_minutes_per_waypoint: float = Field(default=0, ge=0, le=1440, strict=True)
    exposure_duration_min: float | None = Field(default=None, ge=0, le=10080, strict=True)
    radiation_budget_usv: float | None = Field(default=None, ge=0, strict=True)
    required_analyses: list[OptionalAgent] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def unique_requirements(self):
        if len(set(self.required_analyses)) != len(self.required_analyses):
            raise ValueError('Required analyses must be unique.')
        return self


class SpecialistChoice(ContractModel):
    agent_id: OptionalAgent
    selected: bool = Field(strict=True)
    reason: str = Field(min_length=1,max_length=180)


class SpecialistSelection(ContractModel):
    choices: list[SpecialistChoice] = Field(min_length=4,max_length=4)

    @model_validator(mode='after')
    def each_optional_agent(self):
        if {c.agent_id for c in self.choices} != {'A2','A3','A4','A6'}:
            raise ValueError('Every optional specialist must appear exactly once.')
        return self


class SpecialistTrace(ContractModel):
    agent_id: Literal['A1','A2','A3','A4','A6']
    public_name: str
    configured: bool
    selected: bool
    required: bool
    selection_source: Literal['host_policy','user_requirement','a0','deterministic']
    selection_reason: str
    execution_state: Literal['not_requested','succeeded','cached','unavailable','failed']
    data_kind: Literal['observed','scenario','mock','unavailable']
    result_status: Literal['ready','partial','unavailable','failed'] | None = None
    application: Literal['terrain_cost','context_only','dose_scenario','none']
    constraint_status: Literal['pass','fail','unknown'] = 'unknown'
    limitations: list[str] = Field(default_factory=list)
    dataset_ids: list[str] = Field(default_factory=list)
    artifact_id: str | None = None


class TimeEstimate(ContractModel):
    mode: Literal['walking'] = 'walking'
    model: Literal['constant_projected_speed_v1'] = 'constant_projected_speed_v1'
    speed_m_s: float = Field(gt=0)
    travel_min: float = Field(ge=0)
    stop_min: float = Field(ge=0)
    total_min: float = Field(ge=0)
    assumptions: list[str]


class EvidenceQuality(ContractModel):
    """Stable assessment-confidence components, each normalized to [0, 1]."""
    availability: UnitScore
    route_coverage: UnitScore
    temporal_applicability: UnitScore
    validation_provenance: UnitScore

    @property
    def score(self):
        return .25*self.availability+.35*self.route_coverage+.20*self.temporal_applicability+.20*self.validation_provenance


class EvidenceDescription(ContractModel):
    dataset_ids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    dataset_version: str | None = None
    acquisition_time: str | None = None
    observation_period: str | None = None
    route_coverage_fraction: UnitScore | None = None
    uncertainty: str


class RiskFactor(ContractModel):
    agent_id: AssessmentAgentId
    public_name: str = ""
    kind: Literal['risk','context']
    status: Literal['assessed','contextual','unavailable','stale','incompatible','unassessed','not_applicable']
    risk_score: UnitScore | None = None
    evidence_quality: EvidenceQuality
    evidence_ids: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1,max_length=500)
    model_version: str | None = None
    evidence: EvidenceDescription | None = None
    component_reasons: dict[str,str] = Field(default_factory=dict)
    confidence_contribution: PercentScore = 0
    risk_contribution: PercentScore | None = None

    @model_validator(mode='before')
    @classmethod
    def complete_public_name(cls,value):
        if isinstance(value,dict):
            from app.contracts.agent_names import PUBLIC_AGENT_NAMES
            value=dict(value)
            if value.get('agent_id') in PUBLIC_AGENT_NAMES: value['public_name']=PUBLIC_AGENT_NAMES[value['agent_id']]
        return value

    @model_validator(mode='after')
    def grounded_scores_only(self):
        if self.kind == 'risk' and self.status == 'assessed':
            if self.risk_score is None or not self.evidence_ids:
                raise ValueError('An assessed risk factor requires a score and evidence.')
        elif self.risk_score is not None:
            raise ValueError('Only an assessed risk factor may carry a risk score.')
        if self.status in {'unavailable','stale','incompatible','unassessed','not_applicable'} and self.confidence_contribution != 0:
            raise ValueError('Missing/inapplicable evidence cannot contribute confidence.')
        if self.status in {'unavailable','unassessed'} and not self.evidence_ids and self.evidence_quality.score!=0:
            raise ValueError('Unidentified missing evidence cannot have positive quality.')
        if self.status=='not_applicable' and self.evidence_quality.score!=0:
            raise ValueError('Inapplicable factors have no evidence-quality contribution.')
        if self.risk_score is None and self.risk_contribution is not None:
            raise ValueError('An unknown risk cannot have a weighted contribution.')
        return self


class MissionProfile(ContractModel):
    schema_version: Literal['1'] = '1'
    profile_id: MissionProfileId
    version: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
    risk_weights: dict[AssessmentAgentId,UnitScore]
    confidence_weights: dict[AssessmentAgentId,UnitScore]

    @model_validator(mode='after')
    def complete_weights(self):
        required=set(ASSESSMENT_AGENT_IDS)
        if set(self.risk_weights) != required or set(self.confidence_weights) != required:
            raise ValueError('Profiles must explicitly include A1-A6, including A5.')
        if abs(sum(self.risk_weights.values())-1)>1e-9 or abs(sum(self.confidence_weights.values())-1)>1e-9:
            raise ValueError('Profile weights must each sum to exactly 1.')
        if self.version==self.profile_id+'-v2':
            from app.planning.policies import definition, AGENTS
            approved=definition(self.profile_id)
            if self.risk_weights!=dict(zip(AGENTS,approved.risk)) or self.confidence_weights!=dict(zip(AGENTS,approved.confidence)):
                raise ValueError('Versioned profile weights are immutable.')
        return self


class RouteAssessment(ContractModel):
    schema_version: Literal['2'] = '2'
    formula_version: str = 'relative-terrain-scenario-v2'
    score_scale: Literal['0..100'] = '0..100'
    gate_reasons: list[str] = Field(default_factory=list)
    time: TimeEstimate | None = None
    radiation_duration_min: float | None = Field(default=None,ge=0)
    radiation_duration_basis: Literal['user_supplied','route_estimate','unavailable'] = 'unavailable'
    dose_estimate_usv: float | None = Field(default=None,ge=0)
    dose_uncertainty_usv: float | None = Field(default=None,ge=0)
    radiation_constraint_status: Literal['pass','fail','unknown'] = 'unknown'
    required_unassessed: list[OptionalAgent] = Field(default_factory=list)
    required_failed: list[OptionalAgent] = Field(default_factory=list)
    mission_profile: MissionProfile | None = None
    hard_gate_status: Literal['pass','blocked','unassessed'] = 'unassessed'
    risk_score: PercentScore | None = None
    partial_risk_score: PercentScore | None = None
    risk_evidence_coverage: PercentScore | None = None
    assessment_confidence: PercentScore | None = None
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def legacy_score_scale(cls,value):
        profile=value.get('mission_profile') if isinstance(value,dict) else None
        version=profile.get('version','') if isinstance(profile,dict) else getattr(profile,'version','')
        if isinstance(value,dict) and 'schema_version' not in value and version.endswith('-v1'):
            value=dict(value)
            value['formula_version']='legacy-context-quality-v1'
            for key in ('risk_score','assessment_confidence'):
                if value.get(key) is not None: value[key]*=100
        return value

    @model_validator(mode='after')
    def no_risk_past_a_failed_gate(self):
        if self.hard_gate_status != 'pass' and self.risk_score is not None:
            raise ValueError('Blocked or unassessed routes cannot expose a comparable risk score.')
        if self.mission_profile is not None and self.mission_profile.version.endswith('-v2'):
            import math
            if len(self.risk_factors)!=6 or {f.agent_id for f in self.risk_factors}!=set(ASSESSMENT_AGENT_IDS):
                raise ValueError('Versioned assessment must contain A1-A6 exactly once.')
            p=self.mission_profile;by_id={f.agent_id:f for f in self.risk_factors}
            missing=any(w>0 and (by_id[a].status!='assessed' or by_id[a].risk_score is None) for a,w in p.risk_weights.items())
            blocked=self.hard_gate_status=='blocked' or bool(self.required_failed) or self.radiation_constraint_status=='fail'
            expected_gate='blocked' if blocked else 'unassessed' if missing or self.required_unassessed else 'pass'
            if self.hard_gate_status!=expected_gate: raise ValueError('Hard gate must precede factor ranking.')
            denom=sum(w for a,w in p.confidence_weights.items() if by_id[a].status!='not_applicable')
            for f in self.risk_factors:
                expected=100*p.confidence_weights[f.agent_id]*f.evidence_quality.score/denom if f.status in ('assessed','contextual') and denom else 0
                if not math.isclose(f.confidence_contribution,expected,abs_tol=1e-8): raise ValueError('Invalid factor confidence contribution')
                risk=100*p.risk_weights[f.agent_id]*f.risk_score if f.risk_score is not None else None
                if (risk is None)!=(f.risk_contribution is None) or risk is not None and not math.isclose(risk,f.risk_contribution,abs_tol=1e-8):
                    raise ValueError('Invalid risk contribution')
            expected_confidence=sum(f.confidence_contribution for f in self.risk_factors)
            expected_risk=sum(f.risk_contribution or 0 for f in self.risk_factors) if expected_gate=='pass' else None
            if self.assessment_confidence is None or not math.isclose(self.assessment_confidence,expected_confidence,abs_tol=1e-8): raise ValueError('Invalid confidence formula')
            if (expected_risk is None)!=(self.risk_score is None) or expected_risk is not None and not math.isclose(self.risk_score,expected_risk,abs_tol=1e-8):
                raise ValueError('Invalid risk formula')
            # Available-factor score is separate from the complete, gated risk.
            # Missing factors are omitted from numerator AND denominator, never
            # treated as zero risk. Derive it for older stored routes as well.
            weight=sum(p.risk_weights[f.agent_id] for f in self.risk_factors if f.status=='assessed' and f.risk_score is not None)
            partial=min(100.0,max(0.0,sum(f.risk_contribution or 0 for f in self.risk_factors)/weight)) if weight else None
            coverage=min(100.0,100*weight)
            if self.risk_evidence_coverage is not None and not math.isclose(self.risk_evidence_coverage,coverage,abs_tol=1e-8):
                raise ValueError('Invalid available risk coverage')
            if self.partial_risk_score is not None and (partial is None or not math.isclose(self.partial_risk_score,partial,abs_tol=1e-8)):
                raise ValueError('Invalid available-factor risk formula')
            object.__setattr__(self,'partial_risk_score',partial)
            object.__setattr__(self,'risk_evidence_coverage',coverage)
        return self
