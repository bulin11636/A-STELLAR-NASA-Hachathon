"""Persisted registration outcomes contain evidence identifiers, never local paths."""
from typing import Literal
from pydantic import Field, model_validator
from app.contracts.base import ContractModel


class ControlResidual(ContractModel):
    control_id: str
    dem_error_m: float = Field(ge=0)
    wmts_error_m: float = Field(ge=0)
    dem_tolerance_m: float = Field(gt=0)
    wmts_tolerance_m: float = Field(gt=0)
    passed: bool


class MapRegistration(ContractModel):
    schema_version: Literal['1'] = '1'
    method: Literal['independent-feature-controls-v1'] = 'independent-feature-controls-v1'
    map_alignment: Literal['verified','unverified'] = 'unverified'
    source_sha256: str | None = None
    controls_sha256: str | None = None
    capabilities_sha256: str | None = None
    measurement_sha256: str | None = None
    wmts_layer: str | None = None
    wmts_crs: str | None = None
    synthetic: bool = False
    scope: list[tuple[float,float]] = Field(default_factory=list)
    residuals: list[ControlResidual] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evidence_id: str | None = None

    @model_validator(mode='after')
    def controls_before_verification(self):
        if self.map_alignment=='verified' and (not self.source_sha256 or not self.controls_sha256 or not self.capabilities_sha256
            or not self.measurement_sha256 or len(self.residuals)<4 or not all(r.passed for r in self.residuals) or len(self.scope)<3 or self.reasons):
            raise ValueError('Verified registration requires passed, source-bound independent controls and scope.')
        return self
