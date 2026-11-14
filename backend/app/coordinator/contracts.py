"""Internal A0 contracts; the frozen /api/v1 protocol is unchanged."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.contracts.api import COORDINATE_SYSTEM, ContractModel, MarsCoordinate, NonEmptyString
from app.contracts.workers import AgentId, WorkerContext

ToolName = Literal['inspect_capabilities', 'analyze_terrain', 'analyze_thermal', 'estimate_radiation',
                   'find_science_sites', 'inspect_rover_history', 'plan_route', 'validate_route']
Objective = Literal['terrain', 'thermal', 'radiation', 'science', 'rover_history', 'route']


class MissionRequest(ContractModel):
    goal: Annotated[str, Field(strict=True, min_length=1, max_length=4000)]
    context: WorkerContext
    objectives: Annotated[list[Objective], Field(min_length=1, max_length=6)]
    coordinate_system: Literal['MARS_2000_PLANETOCENTRIC_EAST_360_V1'] = COORDINATE_SYSTEM
    start: MarsCoordinate | None = None
    goal_point: MarsCoordinate | None = None

    @model_validator(mode='after')
    def distinct_inputs(self):
        if len(set(self.objectives)) != len(self.objectives):
            raise ValueError('Mission objectives must be unique.')
        if self.start is not None and self.start == self.goal_point:
            raise ValueError('Start and goal must differ.')
        return self


class AgentLimits(ContractModel):
    max_tool_calls: Annotated[int, Field(strict=True, ge=1, le=16)] = 8
    max_replans: Annotated[int, Field(strict=True, ge=0, le=4)] = 2
    tool_timeout_s: Annotated[float, Field(strict=True, gt=0, le=30)] = 10.0
    model_timeout_s: Annotated[float, Field(strict=True, gt=0, le=60)] = 30.0
    mission_timeout_s: Annotated[float, Field(strict=True, gt=0, le=300)] = 120.0


class Proposal(ContractModel):
    action: Literal['execute', 'finish']
    tools: Annotated[list[ToolName], Field(max_length=8)]
    rationale: Annotated[str, Field(strict=True, min_length=1, max_length=500)]
    evidence_ids: Annotated[list[str], Field(max_length=16)]

    @model_validator(mode='after')
    def consistent_action(self):
        if (self.action == 'execute') != bool(self.tools) or len(set(self.tools)) != len(self.tools):
            raise ValueError('Execute requires unique tools; finish requires no tools.')
        return self


class Capability(ContractModel):
    tool: ToolName
    agent_id: AgentId | None
    configured: bool
    readiness: Literal['metadata', 'prototype', 'scenario', 'evidence', 'unavailable']
    description: str


class Evidence(ContractModel):
    evidence_id: str
    tool: ToolName
    agent_id: AgentId | None
    status: Literal['ready', 'partial', 'unavailable', 'failed']
    data_kind: Literal['metadata', 'observed', 'scenario', 'mock', 'unavailable']
    # Whitelisted scalar facts only; no rasters, POI arrays or source instructions.
    facts: dict[str, str | int | float | bool | None]
    dataset_ids: list[str]
    limitations: list[str]


class AuditEvent(ContractModel):
    sequence: int
    event: str
    details: dict[str, str | int | float | bool | None]


class MissionReport(ContractModel):
    run_id: NonEmptyString
    request: MissionRequest
    requested_provider: str
    provider_model: str | None
    limits: AgentLimits
    capabilities: list[Capability]
    fallback_used: bool
    skill_sha256: str
    status: Literal['complete', 'partial', 'blocked', 'budget_exhausted', 'timed_out']
    route_status: Literal['not_requested', 'unavailable']
    summary: str
    evidence: list[Evidence]
    unmet_requirements: list[str]
    limitations: list[str]
    tool_calls: int
    model_calls: int
    decision_calls: int
    replans: int
    audit: list[AuditEvent]
    artifact_index: dict[str, str]
    input_hashes: dict[str, str] = Field(default_factory=dict)
