from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator
from app.contracts.api import ContractModel, MarsCoordinate, MAX_WAYPOINTS, PlanRouteResponse, RouteMode
from app.contracts.routes import RouteMetadata, Usage
from app.contracts.assessment import SpecialistTrace


class AdvancedContext(ContractModel):
    schema_version: Literal['1']
    interface_mode: Literal['advanced']
    route_objective: RouteMode
    required_waypoints: list[MarsCoordinate] = Field(max_length=MAX_WAYPOINTS)
    analysis_focus: list[Literal['terrain', 'science', 'operations']] = Field(
        min_length=1, max_length=3, json_schema_extra={'uniqueItems':True})
    allow_supported_revision: bool = Field(strict=True)

    @model_validator(mode='after')
    def valid_preferences(self):
        if len(set(self.analysis_focus)) != len(self.analysis_focus):
            raise ValueError('Analysis focus must be unique.')
        if any(a == b for a, b in zip(self.required_waypoints, self.required_waypoints[1:])):
            raise ValueError('Consecutive required waypoints must differ.')
        return self

    def require_parent(self, request):
        from app.api.errors import ApiProblem
        fields = []
        if self.route_objective != request.mode:
            fields.append({'field': 'advanced_context.route_objective', 'type': 'parent_route_mismatch'})
        if self.required_waypoints != request.waypoints:
            fields.append({'field': 'advanced_context.required_waypoints', 'type': 'parent_route_mismatch'})
        if fields:
            raise ApiProblem(422, 'ADVANCED_CONTEXT_MISMATCH',
                'Advanced context must match the persisted parent route objective and ordered required waypoints.', details=fields)


class ChatRequest(ContractModel):
    message: Annotated[str, Field(min_length=1,max_length=1600)]
    request_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{16,64}$')]
    advanced_context: AdvancedContext | None = None

    @field_validator('message', mode='before')
    @classmethod
    def trim_message(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChatResponse(ContractModel):
    message_id: str
    route_id: str
    created_at: datetime
    user_message: str
    assistant_message: str
    result: PlanRouteResponse | None = None
    metadata: RouteMetadata | None = None
    usage: Usage | None = None
    specialist_trace: list[SpecialistTrace] = Field(default_factory=list)


class ChatHistory(ContractModel):
    messages: list[ChatResponse]
