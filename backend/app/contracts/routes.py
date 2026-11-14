"""Versioned, finite, nested public metadata for durable computed routes."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.contracts.api import ContractModel, PlanRouteRequest, PlanRouteResponse, NonNegative


class Bounds(ContractModel):
    west: float
    east: float
    south: float
    north: float


class Coordinator(ContractModel):
    agent_id: Literal['A0'] = 'A0'
    public_name: str
    responsibility: str
    implementation_version: str


class Scope(ContractModel):
    region_id: Literal['jezero'] = 'jezero'
    roi_id: str
    dataset_version: str
    bounds: Bounds


class Source(ContractModel):
    dataset_id: str
    source_url: str | None
    input_filename: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    instrument: str | None
    mission: str | None
    acquisition_time: str | None
    provenance_record_id: str


PositiveSpacing = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class GridMetadata(ContractModel):
    grid_id: str
    source_crs: str
    planning_crs: str
    wire_convention: Literal['MARS_2000_PLANETOCENTRIC_EAST_360_V1']
    affine: tuple[float, float, float, float, float, float]
    affine_order: Literal['a,b,c,d,e,f; x=a*column+b*row+c; y=d*column+e*row+f']
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_resolution: tuple[PositiveSpacing, PositiveSpacing]
    planning_resolution_m: tuple[PositiveSpacing, PositiveSpacing]
    vertical_units: Literal['m']
    vertical_scale: float
    vertical_offset: float
    nodata: str | None
    mask_artifact_ids: dict[str, str]


class Limits(ContractModel):
    max_grid_cells: int = Field(gt=0, le=1000000)
    max_expanded_nodes: int = Field(gt=0, le=1000000)
    max_elapsed_seconds: float = Field(gt=0, le=30)


class Policy(ContractModel):
    policy_id: str
    slope_threshold_deg: float = Field(gt=0, lt=90)
    unknown_handling: Literal['impassable'] = 'impassable'
    connectivity: Literal[8] = 8
    corner_cutting: Literal['prohibited'] = 'prohibited'
    endpoint_rule: str
    cost_formula: str
    parameters: dict[str, float]
    limits: Limits


class Planner(ContractModel):
    algorithm: Literal['astar'] = 'astar'
    implementation_version: str
    heuristic: str
    objective_cost: NonNegative
    objective_units: str
    expanded_nodes: int = Field(ge=0)
    elapsed_ms: NonNegative
    distance_convention: str


class Validation(ContractModel):
    status: Literal['passed'] = 'passed'
    validator_version: str
    checks: list[str]
    control_fixture_ids: list[str]
    tolerances: dict[str, float]
    map_alignment: Literal['verified', 'unverified']


class Worker(ContractModel):
    agent_id: Literal['A1', 'A2', 'A3', 'A4', 'A6']
    public_name: str
    responsibility: str
    requested: bool
    status: Literal['ready', 'partial', 'failed', 'unavailable', 'unassessed']
    evidence_kind: Literal['observed', 'scenario', 'mock', 'unavailable']
    dataset_ids: list[str]
    artifact_ids: list[str]
    warnings: list[str]
    unassessed_constraints: list[str]


class Artifact(ContractModel):
    artifact_id: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Usage(ContractModel):
    model: str = 'gpt-6.1-sol'
    reasoning_effort: str = 'medium'
    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: NonNegative = 0
    price_version: str = '2026-11-14-standard-short-context'


class Rationale(ContractModel):
    summary: str
    facts: list[str]
    limitations: list[str]
    model_commentary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class RouteMetadata(ContractModel):
    schema_version: Literal['1'] = '1'
    route_id: str
    created_at: datetime
    request: PlanRouteRequest
    coordinator: Coordinator
    scope: Scope
    sources: list[Source] = Field(min_length=1)
    grid: GridMetadata
    policy: Policy
    planner: Planner
    validation: Validation
    workers: list[Worker]
    artifacts: dict[str, Artifact]
    warnings: list[str] = Field(min_length=1)
    rationale: Rationale | None = None
    usage: Usage | None = None
    parent_route_id: str | None = Field(default=None, pattern=r'^route-[a-f0-9]{32}$')

    @model_validator(mode='after')
    def utc_timestamp(self):
        if self.created_at.utcoffset() is None or self.created_at.utcoffset().total_seconds() != 0:
            raise ValueError('UTC timestamp required')
        return self


class StoredRouteResponse(ContractModel):
    result: PlanRouteResponse
    metadata: RouteMetadata

    @model_validator(mode='after')
    def consistency(self):
        r, m = self.result, self.metadata
        if (r.route_id != m.route_id or r.source != 'computed' or r.mode != m.request.mode
            or r.region_id != m.request.region_id or r.coordinate_system != m.request.coordinate_system
            or r.route[0] != m.request.start or r.route[-1] != m.request.goal
            or r.metrics.distance_m is None or not r.warnings):
            raise ValueError('Inconsistent persisted result')
        index = 0
        for stop in m.request.waypoints:
            while index < len(r.route) and r.route[index] != stop:
                index += 1
            if index == len(r.route):
                raise ValueError('Persisted geometry does not preserve required waypoint order')
            index += 1
        if (m.scope.dataset_version != m.sources[0].sha256 or m.scope.region_id != r.region_id
            or m.grid.wire_convention != r.coordinate_system
            or m.grid.width*m.grid.height > m.policy.limits.max_grid_cells
            or set(m.grid.mask_artifact_ids) != {'coverage','unknown','blocked'}
            or any(ref != r.route_id+':grid#'+role for role,ref in m.grid.mask_artifact_ids.items())
            or set(m.artifacts) != {'grid','validation','provenance'}
            or any(a.artifact_id != r.route_id+':'+role for role,a in m.artifacts.items())
            or m.sources[0].provenance_record_id != r.route_id+':provenance'):
            raise ValueError('Inconsistent provenance or artifact references')
        return self
