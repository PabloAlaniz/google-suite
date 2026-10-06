"""Request IDs, access logs and log formatting for the REST API."""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("gsuite_api.access")

REQUEST_ID_HEADER = "x-request-id"
# Accept caller-supplied IDs (e.g. from a load balancer) only if they are
# short and safe to echo back into headers and logs.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Request ID of the request being handled, if any."""
    return _request_id.get()


class RequestContextMiddleware:
    """Assign a request ID, echo it in X-Request-ID and log one line per request."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        # Also on scope state: error handlers that run outside this middleware
        # (unhandled exceptions) can still read it from request.state.
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id.set(request_id)

        status = 500
        start = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "%s %s %s",
                scope["method"],
                scope["path"],
                status,
                extra={
                    "http_method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


_EXTRA_FIELDS = ("http_method", "path", "status", "duration_ms")


class JsonFormatter(logging.Formatter):
    """One JSON object per line; `severity` is what Cloud Logging reads."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": getattr(record, "request_id", None),
        }
        entry.update({k: getattr(record, k) for k in _EXTRA_FIELDS if hasattr(record, k)})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configure the gsuite loggers; leaves the root logger alone."""
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )

    for name in (
        "gsuite_api",
        "gsuite_core",
        "gsuite_gmail",
        "gsuite_calendar",
        "gsuite_drive",
        "gsuite_sheets",
    ):
        log = logging.getLogger(name)
        log.handlers = [handler]
        log.setLevel(level.upper())
        log.propagate = False
