"""Shared strict contract base, independent of individual request schemas."""
from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, frozen=True,
                              json_schema_serialization_defaults_required=True)
