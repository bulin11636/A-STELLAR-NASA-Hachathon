from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, model_validator

from app.contracts.api import (
    COORDINATE_SYSTEM, ContractModel, CoordinateSystem, MarsCoordinate,
    NonEmptyString, NonNegative,
)

AgentId = Literal["A1", "A2", "A3", "A4", "A6"]
WorkerStatus = Literal["ready", "partial", "unavailable", "failed"]
DataKind = Literal["mock", "observed", "scenario", "unavailable"]
ConstraintStatus = Literal["pass", "fail", "unknown"]
AGENT_IDS: tuple[AgentId, ...] = ("A1", "A2", "A3", "A4", "A6")


class MissionParameters(ContractModel):
    eva_duration_min: NonNegative | None = None
    radiation_budget_usv: NonNegative | None = None


class WorkerContext(ContractModel):
    mission_id: NonEmptyString
    region_id: Literal["jezero"]
    roi_id: NonEmptyString
    dataset_version: NonEmptyString
    parameters: MissionParameters = Field(default_factory=MissionParameters)


class SourceReference(ContractModel):
    dataset_id: NonEmptyString
    source_url: HttpUrl
    mission: NonEmptyString
    instrument: NonEmptyString


class ArtifactMetadata(ContractModel):
    """Metadata only. Arrays/rasters stay outside JSON and LLM context.

    Nullable fields must be recorded as unknown, with reasons in uncertainties.
    Merely constructing this model does not certify a dataset's alignment.
    """

    artifact_id: NonEmptyString
    source: SourceReference
    acquisition_time: datetime | None
    downloaded_at: datetime
    bounding_region: list[MarsCoordinate]
    coordinate_system: CoordinateSystem
    projection: NonEmptyString
    grid_transform: tuple[float, float, float, float, float, float] | None
    resolution_m: Annotated[float, Field(strict=True, gt=0)] | None
    nodata_value: float | str | None
    coverage_ref: str | None
    unknown_mask_ref: str | None
    resampling: NonEmptyString
    processing_version: NonEmptyString
    uncertainties: Annotated[list[str], Field(min_length=1)]


class WorkerResult(ContractModel):
    agent_id: AgentId
    status: WorkerStatus
    data_kind: DataKind
    artifacts: dict[str, str] = Field(default_factory=dict)
    dataset_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance_ref: str | None = None

    @model_validator(mode="after")
    def honest_availability(self):
        if self.data_kind == "mock" and (self.status == "ready" or not self.warnings):
            raise ValueError("Mocks must be partial/unavailable/failed and explicitly warned.")
        if self.status in ("partial", "unavailable", "failed") and not self.warnings:
            raise ValueError("Incomplete workers must explain limitations.")
        if (self.artifacts or self.status == "ready") and not self.provenance_ref:
            raise ValueError("Artifacts and ready outputs require a provenance reference.")
        if self.status == "ready" and (not self.dataset_ids or self.data_kind == "unavailable"):
            raise ValueError("Ready outputs require identified inputs.")
        return self


class SurfaceResult(WorkerResult):
    agent_id: Literal["A1"] = "A1"
    grid_id: str | None = None
    slope_ref: str | None = None
    roughness_ref: str | None = None
    risk_ref: str | None = None
    hard_block_ref: str | None = None
    coverage_ref: str | None = None
    unknown_ref: str | None = None
    geospatial_metadata_ref: str | None = None


class ThermalResult(WorkerResult):
    agent_id: Literal["A2"] = "A2"
    observed_at: datetime | None = None
    observation_unit: str | None = None
    coverage_ref: str | None = None
    thermal_raster_ref: str | None = None
    constraint_status: ConstraintStatus = "unknown"


class RadiationResult(WorkerResult):
    agent_id: Literal["A3"] = "A3"
    dose_rate_usv_per_hour: NonNegative | None = None
    duration_min: NonNegative | None = None
    dose_estimate_usv: NonNegative | None = None
    dose_uncertainty_usv: NonNegative | None = None
    budget_usv: NonNegative | None = None
    constraint_status: ConstraintStatus = "unknown"
    model_reference: str | None = None

    @model_validator(mode="after")
    def no_unavailable_dose(self):
        if self.status in ("unavailable", "failed") and (
            self.dose_estimate_usv is not None or self.constraint_status != "unknown"
        ):
            raise ValueError("Unavailable radiation is unknown, not a numeric dose or passing constraint.")
        if self.dose_estimate_usv is not None and (
            self.model_reference is None or self.dose_rate_usv_per_hour is None or self.duration_min is None
        ):
            raise ValueError("A numeric radiation scenario requires a documented rate, duration and model.")
        return self


class SciencePOI(MarsCoordinate):
    id: NonEmptyString
    coordinate_system: CoordinateSystem = COORDINATE_SYSTEM
    category: NonEmptyString
    source: SourceReference
    rationale: NonEmptyString
    priority: Annotated[float, Field(strict=True, ge=0, le=1)] | None = None
    priority_method: str | None = None

    @model_validator(mode="after")
    def documented_ranking(self):
        if self.priority is not None and not self.priority_method:
            raise ValueError("A normalized priority requires a documented scoring method.")
        return self


class ScienceResult(WorkerResult):
    agent_id: Literal["A4"] = "A4"
    pois: list[SciencePOI] = Field(default_factory=list)
    geology_ref: str | None = None
    ranking_method: str | None = None


class RoverStop(MarsCoordinate):
    sol: Annotated[int, Field(strict=True, ge=0)]
    source: SourceReference
    observation_urls: list[HttpUrl] = Field(default_factory=list)


class RoverTraverseResult(WorkerResult):
    agent_id: Literal["A6"] = "A6"
    stops: list[RoverStop] = Field(default_factory=list)
    traverse_ref: str | None = None
    data_timestamp: datetime | None = None
    coverage_ref: str | None = None
    nearest_track_distance_m: NonNegative | None = None
    coordinate_system: CoordinateSystem = COORDINATE_SYSTEM


RESULT_TYPES = {
    "A1": SurfaceResult, "A2": ThermalResult, "A3": RadiationResult,
    "A4": ScienceResult, "A6": RoverTraverseResult,
}
