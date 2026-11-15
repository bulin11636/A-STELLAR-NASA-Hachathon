"""Walking assumptions and auditable specialist decisions; no safety defaults."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.contracts.base import ContractModel

OptionalAgent = Literal['A2','A3','A4','A6']
AssessmentAgentId = Literal['A1','A2','A3','A4','A5','A6']
MissionProfileId = Literal['safest','fastest','science_priority','balanced']
UnitScore = Annotated[float, Field(strict=True,ge=0,le=1,allow_inf_nan=False)]
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


class RiskFactor(ContractModel):
    agent_id: AssessmentAgentId
    kind: Literal['risk','context']
    status: Literal['assessed','contextual','unavailable','stale','incompatible','unassessed','not_applicable']
    risk_score: UnitScore | None = None
    evidence_quality: EvidenceQuality
    evidence_ids: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1,max_length=500)

    @model_validator(mode='after')
    def grounded_scores_only(self):
        if self.kind == 'risk' and self.status == 'assessed':
            if self.risk_score is None or not self.evidence_ids:
                raise ValueError('An assessed risk factor requires a score and evidence.')
        elif self.risk_score is not None:
            raise ValueError('Only an assessed risk factor may carry a risk score.')
        if self.status in {'unavailable','stale','incompatible','unassessed','not_applicable'} and self.evidence_quality.score != 0:
            raise ValueError('Unavailable or unassessed evidence must have zero quality.')
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
        return self


class RouteAssessment(ContractModel):
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
    risk_score: UnitScore | None = None
    assessment_confidence: UnitScore | None = None
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def no_risk_past_a_failed_gate(self):
        if self.hard_gate_status != 'pass' and self.risk_score is not None:
            raise ValueError('Blocked or unassessed routes cannot expose a comparable risk score.')
        return self
