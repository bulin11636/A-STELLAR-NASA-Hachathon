from fastapi import APIRouter, Request, Response, Header, Path
from typing import Annotated
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from app.contracts.routes import StoredRouteResponse
from app.contracts.chat import ChatRequest, ChatResponse, ChatHistory
from app.contracts.attempts import REQUEST_ID_PATTERN, RequestAttemptStatus

RequestId = Annotated[str,Path(pattern=REQUEST_ID_PATTERN)]

from app.api.errors import ApiProblem
from app.contracts.api import (
    COORDINATE_SYSTEM, ErrorEnvelope, HealthResponse, PlanRouteRequest,
    PlanRouteResponse, RegionsResponse,
)

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    return HealthResponse()


@router.get("/ready", tags=["health"])
async def readiness(request: Request):
    """Local configuration readiness only; never contact the model provider."""
    planning = request.app.state.planning
    settings = request.app.state.route_agent.settings
    checks = {
        "planning": bool(await run_in_threadpool(lambda: planning.ready)),
        "model_credentials": not settings.enabled or bool(settings.api_key),
    }
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503, content={
        "status": "ready" if ready else "not_ready",
        "routing_mode": planning.mode,
        "a0_mode": "agentic" if settings.enabled else "deterministic",
        "checks": checks,
    })


@router.get("/regions", response_model=RegionsResponse, tags=["regions"])
async def regions(request: Request):
    service = request.app.state.planning
    region = await run_in_threadpool(service.describe_region)
    return RegionsResponse(regions=[region])


@router.post("/routes/plan", response_model=PlanRouteResponse, tags=["routes"], responses={
    status: {"model": ErrorEnvelope} for status in (400, 404, 409, 422, 429, 500, 503)
})
async def plan_route(body: PlanRouteRequest, request: Request,
                     idempotency_key: str | None = Header(default=None,alias='Idempotency-Key',pattern=REQUEST_ID_PATTERN),
                     retry_attempt: int | None = Header(default=None,alias='X-A-Stellar-Retry-Attempt',ge=1)):
    if body.coordinate_system != COORDINATE_SYSTEM:
        raise ApiProblem(400, "UNSUPPORTED_COORDINATE_SYSTEM", "The requested Mars coordinate convention is not supported.")
    if body.region_id != "jezero":
        raise ApiProblem(404, "UNKNOWN_REGION", "The requested region is not supported.")
    if body.start == body.goal:
        raise ApiProblem(400, "INVALID_ROUTE", "Start and Goal must be different points.")
    if retry_attempt is not None and idempotency_key is None:
        raise ApiProblem(400,'IDEMPOTENCY_KEY_REQUIRED','Explicit plan retries require the original Idempotency-Key.')
    if request.app.state.planning.mode == "computed":
        if idempotency_key is not None:
            return await run_in_threadpool(request.app.state.plan_requests.plan,body,idempotency_key,retry_attempt)
        return await run_in_threadpool(request.app.state.route_agent.plan, body)
    if idempotency_key is not None:
        raise ApiProblem(400,'IDEMPOTENCY_REQUIRES_COMPUTED','Persistent plan idempotency requires computed routing.')
    return await request.app.state.coordinator.plan_mock_route(body)


@router.get('/routes/requests/{request_id}',response_model=RequestAttemptStatus,tags=['routes'],responses={
    status: {'model':ErrorEnvelope} for status in (404,409,422,500,503)
})
async def plan_request_status(request_id: RequestId,request: Request,response: Response):
    response.headers['Cache-Control']='no-store'
    return await run_in_threadpool(request.app.state.plan_requests.status,request_id)


@router.get("/routes/{route_id}", response_model=StoredRouteResponse, tags=["routes"], responses={
    status: {"model": ErrorEnvelope} for status in (404, 422, 500)
})
async def stored_route(route_id: str, request: Request):
    return await run_in_threadpool(request.app.state.planning.store.get, route_id)


@router.get('/a0/status', tags=['agents'])
async def agent_status(request: Request):
    agent=request.app.state.route_agent
    result=dict(mode='agentic' if agent.settings.enabled else 'deterministic',model=agent.settings.model,
        reasoning_effort='medium',configured=bool(agent.settings.api_key),max_output_tokens=agent.settings.max_output_tokens)
    if agent.settings.enabled:
        result['budget']=await run_in_threadpool(agent.provider.totals)
        result['last_provider_error']=await run_in_threadpool(agent.provider.last_failure)
    return result


@router.post('/routes/{route_id}/chat',response_model=ChatResponse,tags=['chat'],responses={
    status: {'model':ErrorEnvelope} for status in (400,404,409,422,429,500,503)
})
async def chat_route(route_id: str,body: ChatRequest,request: Request,
                     retry_attempt: int | None = Header(default=None,alias='X-A-Stellar-Retry-Attempt',ge=1)):
    return await run_in_threadpool(request.app.state.chat.send,route_id,body,retry_attempt=retry_attempt)


@router.get('/routes/{route_id}/chat/attempts/{request_id}',response_model=RequestAttemptStatus,tags=['chat'],responses={
    status: {'model':ErrorEnvelope} for status in (404,409,422,500,503)
})
async def chat_attempt_status(route_id: str,request_id: RequestId,request: Request,response: Response):
    response.headers['Cache-Control']='no-store'
    return await run_in_threadpool(request.app.state.chat.status,route_id,request_id)


@router.get('/routes/{route_id}/chat',response_model=ChatHistory,tags=['chat'])
async def route_chat_history(route_id: str,request: Request):
    return await run_in_threadpool(request.app.state.chat.history,route_id)
