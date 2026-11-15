"""Additional status endpoint; existing plan/chat payloads remain unchanged."""
from datetime import datetime
from typing import Literal
from pydantic import Field
from app.contracts.api import ContractModel, ErrorBody

REQUEST_ID_PATTERN = r'^[A-Za-z0-9_-]{16,64}$'


class RequestAttemptStatus(ContractModel):
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    state: Literal['running','succeeded','failed','unknown']
    attempt: int = Field(ge=1)
    retry_allowed: bool
    retry_after_seconds: int = Field(ge=0)
    error: ErrorBody | None = None
    updated_at: datetime | None = None
