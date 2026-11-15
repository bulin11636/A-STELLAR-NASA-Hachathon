from typing import Annotated, Literal

from pydantic import Field, model_validator
from app.contracts.base import ContractModel
from app.contracts.assessment import WalkingMission

COORDINATE_SYSTEM = "MARS_2000_PLANETOCENTRIC_EAST_360_V1"
MAX_WAYPOINTS = 16
CoordinateSystem = Literal["MARS_2000_PLANETOCENTRIC_EAST_360_V1"]
RouteMode = Literal["shortest", "safest"]
NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
NonNegative = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class MarsCoordinate(ContractModel):
    """Named API fields; east-positive [0,360), planetocentric [-90,90]."""

    longitude: Annotated[float, Field(strict=True, ge=0, lt=360)]
    latitude: Annotated[float, Field(strict=True, ge=-90, le=90)]


class PlanRouteRequest(ContractModel):
    # Keep semantic mismatches as strings here so the boundary can return the
    # contract's 400/404 instead of Pydantic's structural 422 response.
    region_id: NonEmptyString
    coordinate_system: NonEmptyString
    start: MarsCoordinate
    goal: MarsCoordinate
    mode: RouteMode
    waypoints: Annotated[list[MarsCoordinate], Field(max_length=MAX_WAYPOINTS)] = Field(default_factory=list)

    mission: WalkingMission | None = None
    mission_profile: Literal['safest','fastest','science_priority','balanced'] = 'balanced'

    @model_validator(mode="after")
    def distinct_stops(self):
        stops = [self.start, *self.waypoints, self.goal]
        if self.waypoints and any(a == b for a, b in zip(stops, stops[1:])):
            raise ValueError('Consecutive route stops must differ.')
        return self


class RouteMetrics(ContractModel):
    distance_m: NonNegative | None = None
    estimated_time_min: NonNegative | None = None
    risk_score: Annotated[float, Field(strict=True, ge=0, le=1)] | None = None


class PlanRouteResponse(ContractModel):
    status: Literal["success"] = "success"
    route_id: NonEmptyString
    region_id: Literal["jezero"] = "jezero"
    coordinate_system: CoordinateSystem = COORDINATE_SYSTEM
    mode: RouteMode
    source: Literal["mock", "computed"]
    route: Annotated[list[MarsCoordinate], Field(min_length=2)]
    metrics: RouteMetrics
    warnings: list[str]

    @model_validator(mode="after")
    def honest_mock(self):
        if self.source == "mock":
            if any(value is not None for value in self.metrics.model_dump().values()):
                raise ValueError("Mock route metrics must remain null.")
            if not any(warning.strip() for warning in self.warnings):
                raise ValueError("Mock routes require an explicit warning.")
        return self


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    service: Literal["a-stellar-backend"] = "a-stellar-backend"
    api_version: Literal["v1"] = "v1"


class PlanningBounds(ContractModel):
    west: float
    east: float
    south: float
    north: float


class PlanningInfo(ContractModel):
    roi_id: NonEmptyString
    bounds: PlanningBounds
    resolution_m: tuple[float, float]
    example_request: PlanRouteRequest | None = None
    regional_example_request: PlanRouteRequest | None = None
    source_bounds: PlanningBounds | None = None
    dynamic_windowing: bool = False
    max_grid_cells: int | None = None


class Region(ContractModel):
    id: Literal["jezero"] = "jezero"
    name: Literal["Jezero Crater"] = "Jezero Crater"
    coordinate_system: CoordinateSystem = COORDINATE_SYSTEM
    routing_available: bool = True
    routing_mode: Literal["mock", "computed"] = "mock"
    planning: PlanningInfo | None = None


class RegionsResponse(ContractModel):
    regions: list[Region]


class ErrorBody(ContractModel):
    code: str
    message: str
    details: list[dict[str, str]] | None = None


class ErrorEnvelope(ContractModel):
    error: ErrorBody
