"""Error responses as RFC 9457 problem details (application/problem+json).

Routes don't catch exceptions. SDK errors (GSuiteError) are mapped to HTTP
statuses here, and anything unexpected becomes a 500 that carries the
request ID but never the exception text.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from googleapiclient.errors import HttpError
from starlette.exceptions import HTTPException as StarletteHTTPException

from gsuite_api.observability import get_request_id
from gsuite_core.api_utils import map_http_error
from gsuite_core.exceptions import (
    APIError,
    AuthenticationError,
    GSuiteError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    ValidationError,
)

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


def problem(
    request: Request,
    status: int,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build a problem details response."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "instance": request.url.path,
        # request.state survives into handlers that run after the request
        # middleware has exited (unhandled exceptions); the contextvar doesn't.
        "request_id": getattr(request.state, "request_id", None) or get_request_id(),
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_JSON)


def _gsuite_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GSuiteError)

    # Order matters: the specific APIError subclasses come before APIError.
    if isinstance(exc, RateLimitError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return problem(request, 429, exc.message, headers=headers, service=exc.service)
    if isinstance(exc, QuotaExceededError):
        return problem(request, 429, exc.message, service=exc.service)
    if isinstance(exc, NotFoundError):
        return problem(request, 404, exc.message, service=exc.service)
    if isinstance(exc, PermissionDeniedError):
        return problem(request, 403, exc.message, service=exc.service)
    if isinstance(exc, APIError):
        # Google failed in a way we don't map; the message can carry request
        # URLs and IDs from upstream, so log it and return a generic detail.
        logger.error("Upstream %s API error: %s", exc.service, exc.message)
        return problem(
            request,
            502,
            f"Google {exc.service} API error",
            service=exc.service,
            upstream_status=exc.status_code,
        )
    if isinstance(exc, AuthenticationError):
        # The server has no usable Google token; the caller can't fix that
        # with their API key, but 401 is what clients of this API expect.
        return problem(request, 401, exc.message)
    if isinstance(exc, ValidationError):
        return problem(request, 422, exc.message, field=exc.field)

    logger.exception("Unhandled SDK error", exc_info=exc)
    return problem(request, 500, "Internal error")


def _google_http_error(request: Request, exc: Exception) -> JSONResponse:
    # Client methods not wrapped in @api_call leak raw HttpErrors; map them
    # the same way the decorator would. The service is the route prefix.
    assert isinstance(exc, HttpError)
    service = request.url.path.strip("/").split("/", 1)[0] or "google"
    return _gsuite_error(request, map_http_error(exc, service))


def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    headers = dict(exc.headers) if exc.headers else None
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem(request, exc.status_code, detail, headers=headers)


def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
        for e in exc.errors()
    ]
    return problem(request, 422, "Request validation failed", errors=errors)


def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return problem(request, 500, "Internal error")


def install_error_handlers(app: FastAPI) -> None:
    """Register problem-details handlers on the app."""
    app.add_exception_handler(GSuiteError, _gsuite_error)
    app.add_exception_handler(HttpError, _google_http_error)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
