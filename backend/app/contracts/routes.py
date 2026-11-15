"""Versioned, finite, nested public metadata for durable computed routes."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.contracts.api import ContractModel, PlanRouteRequest, PlanRouteResponse, NonNegative
from app.contracts.assessment import SpecialistTrace, RouteAssessment
from app.contracts.registration import MapRegistration


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


class RouteLeg(ContractModel):
    index: int = Field(ge=1)
    distance_m: NonNegative
    travel_time_min: NonNegative | None = None
    stop_time_min: NonNegative = 0


class AppliedPlanningPolicy(ContractModel):
    version: str
    mission_profile_id: str
    mission_profile_version: str
    legacy_objective: bool
    resolution_profile: Literal['coarse','standard','fine','legacy']
    resolution_version: str = 'resolution-v1'
    minimum_native_factor: int = Field(ge=1)
    actual_native_factor: int = Field(ge=1)
    actual_cell_size_m: tuple[PositiveSpacing,PositiveSpacing]
    source_cell_size_m: tuple[PositiveSpacing,PositiveSpacing]
    terrain_weight: NonNegative
    limits: Limits
    eta_model: Literal['constant_projected_speed_v1'] = 'constant_projected_speed_v1'


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

    specialist_trace: list[SpecialistTrace] = Field(default_factory=list)
    assessment: RouteAssessment | None = None
    planning_policy: AppliedPlanningPolicy | None = None
    legs: list[RouteLeg] = Field(default_factory=list)
    registration: MapRegistration | None = None

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
        if m.assessment is not None:
            import math
            expected=m.assessment.time.total_min if m.assessment.time else None
            actual=r.metrics.estimated_time_min
            if (expected is None) != (actual is None) or expected is not None and not math.isclose(expected,actual,rel_tol=1e-9,abs_tol=1e-9):
                raise ValueError('Walking assessment and route time disagree')
            if m.assessment.time is not None:
                estimate=m.assessment.time;mission=m.request.mission
                if mission is None or mission.speed_m_s != estimate.speed_m_s:
                    raise ValueError('Walking estimate requires matching explicit mission assumptions')
                travel=r.metrics.distance_m/mission.speed_m_s/60
                stop=len(m.request.waypoints)*mission.stop_minutes_per_waypoint
                if not all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9) for a,b in
                    [(estimate.travel_min,travel),(estimate.stop_min,stop),(estimate.total_min,travel+stop)]):
                    raise ValueError('Walking estimate does not match the route distance and dwell assumptions')
        if m.registration is not None:
            if m.registration.map_alignment!=m.validation.map_alignment or m.registration.source_sha256!=m.sources[0].sha256:
                raise ValueError('Registration and source validation disagree')
            if m.registration.map_alignment=='verified':
                from app.planning.registration import covered
                polygon=[tuple(p) for p in m.registration.scope]
                if not all(covered(polygon,(p.longitude,p.latitude),1e-14) for p in r.route):
                    raise ValueError('Persisted route leaves the registration control footprint')
            if m.registration.evidence_id!=r.route_id+':provenance#registration':
                raise ValueError('Registration evidence reference mismatch')
        if m.planning_policy is not None:
            import math
            from app.planning.policies import POLICY_VERSION, selected_profile
            applied=m.planning_policy
            if (applied.version!=POLICY_VERSION or applied.mission_profile_id!=selected_profile(m.request)
                or applied.limits!=m.policy.limits or applied.actual_cell_size_m!=m.grid.planning_resolution_m
                or applied.source_cell_size_m!=m.grid.source_resolution
                or applied.terrain_weight!=m.policy.parameters['weight']
                or m.assessment is None or applied.mission_profile_version!=m.assessment.mission_profile.version):
                raise ValueError('Stored planning policy disagrees with request, assessment or grid')
            if len(m.legs)!=len(m.request.waypoints)+1 or [leg.index for leg in m.legs]!=list(range(1,len(m.legs)+1)):
                raise ValueError('Incomplete ordered leg metadata')
            if not math.isclose(sum(leg.distance_m for leg in m.legs),r.metrics.distance_m,rel_tol=1e-9,abs_tol=1e-6):
                raise ValueError('Leg distances disagree with total distance')
            if m.assessment.time and not math.isclose(sum((leg.travel_time_min or 0)+leg.stop_time_min for leg in m.legs),m.assessment.time.total_min,rel_tol=1e-9,abs_tol=1e-8):
                raise ValueError('Leg time disagrees with walking assumptions')
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
