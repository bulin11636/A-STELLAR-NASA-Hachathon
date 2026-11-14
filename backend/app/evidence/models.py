from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, model_validator

from app.contracts.api import ContractModel, MarsCoordinate, NonEmptyString
from app.contracts.workers import RoverStop, SciencePOI, WorkerContext


class EvidenceRoi(ContractModel):
    """Explicit evidence selection window; never proof of DEM coverage."""

    roi_id: Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")]
    west: Annotated[float, Field(ge=0, lt=360)]
    east: Annotated[float, Field(ge=0, lt=360)]
    south: Annotated[float, Field(ge=-90, le=90)]
    north: Annotated[float, Field(ge=-90, le=90)]

    @model_validator(mode="after")
    def local_extent(self):
        if not 0 < (self.east - self.west) % 360 <= 4 or not 0 < self.north - self.south <= 4:
            raise ValueError("Evidence ROI must be local: positive span at most four degrees per axis.")
        return self

    def contains(self, point: MarsCoordinate) -> bool:
        return ((point.longitude - self.west) % 360 <= (self.east - self.west) % 360 and
                self.south <= point.latitude <= self.north)

    @property
    def center(self) -> MarsCoordinate:
        return MarsCoordinate(longitude=(self.west + (self.east - self.west) % 360 / 2) % 360,
                              latitude=(self.south + self.north) / 2)


PREVIEW_ROI = EvidenceRoi(roi_id="jezero-evidence-preview-v1", west=77.15, east=77.60, south=18.20, north=18.70)


class Snapshot(ContractModel):
    file_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+\.(json|csv|xml)$")]
    source_url: HttpUrl
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    downloaded_at: datetime
    credit: NonEmptyString
    usage_terms_url: HttpUrl


class SnapshotManifest(ContractModel):
    format_version: Literal["1"] = "1"
    dataset_version: NonEmptyString
    snapshots: dict[str, Snapshot]


class LocalizedStop(RoverStop):
    record_id: NonEmptyString


class TrackSegment(ContractModel):
    record_id: NonEmptyString
    sol: Annotated[int, Field(strict=True, ge=0)]
    points: Annotated[list[MarsCoordinate], Field(min_length=2)]


class EvidenceDataset(ContractModel):
    dataset_version: NonEmptyString
    roi: EvidenceRoi
    stops: list[LocalizedStop]
    segments: list[TrackSegment]
    pois: list[SciencePOI]
    dataset_ids: list[str]
    warnings: list[str]
    provenance_ref: NonEmptyString
    # A local reference, not a new external GeoJSON/WGS84 API contract.
    artifact_ref: NonEmptyString


def context_matches(dataset: EvidenceDataset, context: WorkerContext) -> bool:
    return (context.region_id == "jezero" and context.roi_id == dataset.roi.roi_id
            and context.dataset_version == dataset.dataset_version)
