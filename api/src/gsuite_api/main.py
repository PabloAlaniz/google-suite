"""FastAPI application - Unified Google Suite API Gateway."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gsuite_api.dependencies import require_api_key
from gsuite_api.errors import install_error_handlers
from gsuite_api.observability import RequestContextMiddleware, configure_logging
from gsuite_api.routes import calendar, contacts, drive, gmail, health, sheets, tasks
from gsuite_core import Settings, __version__, get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    settings: Settings = app.state.settings
    configure_logging(settings.log_level, settings.log_format)
    if not settings.api_key:
        if settings.allow_no_api_key:
            logger.warning("GSUITE_ALLOW_NO_API_KEY is set: the API accepts requests without a key")
        else:
            logger.warning("GSUITE_API_KEY is not set: every API request will be rejected")
    logger.info("Google Suite API %s starting", __version__)
    yield
    logger.info("Google Suite API shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application."""
    settings = settings or get_settings()

    app = FastAPI(
        title="Google Suite API",
        description=(
            "Unified REST API for Google Workspace - Gmail, Calendar, Drive, Sheets, Tasks, Contacts"
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings

    install_error_handlers(app)

    # Off unless origins are configured. Auth is the X-API-Key header, not
    # cookies, so credentials are never allowed.
    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    # Added last so it wraps everything, CORS preflights included.
    app.add_middleware(RequestContextMiddleware)

    # The API key is enforced per router, so a new route can't forget it.
    protected = [Depends(require_api_key)]
    app.include_router(health.router)
    app.include_router(gmail.router, prefix="/gmail", tags=["Gmail"], dependencies=protected)
    app.include_router(
        calendar.router, prefix="/calendar", tags=["Calendar"], dependencies=protected
    )
    app.include_router(drive.router, prefix="/drive", tags=["Drive"], dependencies=protected)
    app.include_router(sheets.router, prefix="/sheets", tags=["Sheets"], dependencies=protected)
    app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"], dependencies=protected)
    app.include_router(
        contacts.router, prefix="/contacts", tags=["Contacts"], dependencies=protected
    )

    return app


app = create_app()


def run() -> None:
    """Run the API server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
