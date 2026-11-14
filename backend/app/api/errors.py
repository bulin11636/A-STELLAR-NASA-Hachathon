import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.contracts.api import ErrorBody, ErrorEnvelope

logger = logging.getLogger(__name__)


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str, *, details=None,
                 retry_safe=False, outcome_unknown=False, retry_after_seconds=None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.retry_safe = retry_safe
        self.outcome_unknown = outcome_unknown
        self.retry_after_seconds = retry_after_seconds


def error_response(status: int, code: str, message: str, details=None) -> JSONResponse:
    envelope = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status, content=envelope.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def domain_error(_request: Request, error: ApiProblem):
        return error_response(error.status, error.code, error.message, error.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Omit raw input/context: they can include nonfinite numbers, secrets or
        # exception objects that are unsuitable for JSON and client display.
        details = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]} for item in error.errors()]
        return error_response(422, "VALIDATION_ERROR", "The request does not match the API contract.", details)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return error_response(error.status_code, codes.get(error.status_code, "HTTP_ERROR"), "The requested endpoint or method is unavailable.")

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, error: Exception):
        logger.error("Unhandled API failure", exc_info=error)
        return error_response(500, "INTERNAL_ERROR", "An unexpected backend error occurred.")
