from datetime import datetime
from typing import Annotated
from pydantic import Field
from app.contracts.api import ContractModel, PlanRouteResponse
from app.contracts.routes import RouteMetadata, Usage


class ChatRequest(ContractModel):
    message: Annotated[str, Field(min_length=1,max_length=1600)]
    request_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{16,64}$')]


class ChatResponse(ContractModel):
    message_id: str
    route_id: str
    created_at: datetime
    user_message: str
    assistant_message: str
    result: PlanRouteResponse | None = None
    metadata: RouteMetadata | None = None
    usage: Usage | None = None


class ChatHistory(ContractModel):
    messages: list[ChatResponse]
