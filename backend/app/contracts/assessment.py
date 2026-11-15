"""Walking assumptions and auditable specialist decisions; no safety defaults."""
from typing import Literal
from pydantic import Field, model_validator
from app.contracts.base import ContractModel

OptionalAgent = Literal['A2','A3','A4','A6']


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


class RouteAssessment(ContractModel):
    time: TimeEstimate | None = None
    radiation_duration_min: float | None = Field(default=None,ge=0)
    radiation_duration_basis: Literal['user_supplied','route_estimate','unavailable'] = 'unavailable'
    dose_estimate_usv: float | None = Field(default=None,ge=0)
    dose_uncertainty_usv: float | None = Field(default=None,ge=0)
    radiation_constraint_status: Literal['pass','fail','unknown'] = 'unknown'
    required_unassessed: list[OptionalAgent] = Field(default_factory=list)
    required_failed: list[OptionalAgent] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
