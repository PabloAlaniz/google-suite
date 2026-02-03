"""FastAPI application - Unified Google Suite API Gateway."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gsuite_api.routes import calendar, drive, gmail, health, sheets
from gsuite_core import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print("🚀 Google Suite API starting up...")
    yield
    print("👋 Google Suite API shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Google Suite API",
        description="Unified REST API for Google Workspace - Gmail, Calendar, Drive, Sheets",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(health.router)
    app.include_router(gmail.router, prefix="/gmail", tags=["Gmail"])
    app.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
    app.include_router(drive.router, prefix="/drive", tags=["Drive"])
    app.include_router(sheets.router, prefix="/sheets", tags=["Sheets"])

    return app


app = create_app()


def run():
    """Run the API server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "gsuite_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    run()
