"""Bounded policy discovery for frontend profile/resolution controls."""
from typing import Literal
from pydantic import Field
from app.contracts.base import ContractModel
from app.contracts.assessment import AssessmentAgentId, MissionProfile


class MissionPolicyOption(MissionProfile):
    mode: Literal['shortest','safest']
    terrain_weight_multiplier: float = Field(ge=0,le=100)
    default_resolution: Literal['coarse','standard','fine']
    eta_model: Literal['constant_projected_speed_v1']
    requires_user_speed: Literal[True]
    required_risk_factors: list[AssessmentAgentId]
    limitations: list[str]


class ResolutionOption(ContractModel):
    profile_id: Literal['coarse','standard','fine']
    version: Literal['resolution-v1']
    minimum_native_factor: int = Field(ge=1,le=32)
    max_grid_cells: int = Field(gt=0,le=1000000)
    max_expanded_nodes: int = Field(gt=0,le=1000000)
    max_elapsed_seconds: float = Field(gt=0,le=30)
    bounds: str


class PolicyCatalog(ContractModel):
    schema_version: Literal['2']
    policy_version: Literal['jezero-walking-policy-v2']
    formula_version: Literal['relative-terrain-scenario-v2']
    score_scale: Literal['0..100']
    mission_mode: Literal['walking']
    profiles: list[MissionPolicyOption] = Field(min_length=4,max_length=4)
    resolutions: list[ResolutionOption] = Field(min_length=3,max_length=3)
