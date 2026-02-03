"""Health check routes."""

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import APIKeyHeader

from gsuite_api.dependencies import AuthDep
from gsuite_core import get_settings

router = APIRouter(tags=["Health"])

# Admin API key for logs endpoint
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def verify_admin_key(
    admin_key: str | None = Security(admin_key_header),
    api_key: str | None = Query(None, alias="api_key"),
) -> str:
    """Verify admin API key from header or query param."""
    key = admin_key or api_key
    expected = os.environ.get("ADMIN_API_KEY")

    if not expected:
        raise HTTPException(status_code=503, detail="Admin API key not configured")

    if not key or key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    return key


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "service": "gsuite-api",
        "version": settings.version,
    }


@router.get("/health/auth")
async def auth_status(auth: AuthDep):
    """Check authentication status."""
    return {
        "authenticated": auth.is_authenticated(),
        "needs_refresh": auth.needs_refresh(),
    }


@router.get("/health/admin/logs")
async def get_logs(
    _admin: str = Security(verify_admin_key),
    severity: str = Query("ERROR", description="Minimum severity: DEBUG, INFO, WARNING, ERROR"),
    limit: int = Query(50, ge=1, le=500),
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
):
    """
    Fetch recent logs from Cloud Logging.

    Requires X-Admin-Key header or api_key query param.
    """
    try:
        from google.cloud import logging as cloud_logging
    except ImportError:
        raise HTTPException(status_code=503, detail="google-cloud-logging not installed")

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    service_name = os.environ.get("K_SERVICE", "google-suite")

    if not project_id:
        raise HTTPException(status_code=503, detail="GCP project not configured")

    try:
        client = cloud_logging.Client(project=project_id)

        # Calculate time filter
        now = datetime.now(UTC)
        start_time = now - timedelta(hours=hours)

        # Build filter - severity uses name not number
        severity_upper = severity.upper()
        if severity_upper not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            severity_upper = "ERROR"

        filter_str = f"""
            resource.type="cloud_run_revision"
            resource.labels.service_name="{service_name}"
            timestamp>="{start_time.isoformat()}"
            severity>={severity_upper}
        """

        entries = list(
            client.list_entries(
                filter_=filter_str,
                order_by=cloud_logging.DESCENDING,
                max_results=limit,
            )
        )

        logs = []
        for entry in entries:
            payload = entry.payload
            if isinstance(payload, dict):
                message = payload.get("message", str(payload))
            else:
                message = str(payload) if payload else ""

            logs.append(
                {
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "severity": entry.severity or "DEFAULT",
                    "message": message[:2000],  # Truncate long messages
                }
            )

        return {
            "service": service_name,
            "project": project_id,
            "filter": {
                "severity": severity,
                "hours": hours,
                "limit": limit,
            },
            "count": len(logs),
            "logs": logs,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")
