"""Health check endpoints for system diagnostics and monitoring."""

import os
import platform
import time
from fastapi import APIRouter
from pydantic import BaseModel
from src.publisher.core.config import settings

router = APIRouter(prefix="/api", tags=["Health"])

START_TIME = time.time()


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str
    host_binding: str
    platform: str
    uptime_seconds: float
    database_connected: bool


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return system health, runtime metrics, and configuration status."""
    # Check if database directory/file is accessible
    db_ok = os.path.exists(settings.DATA_DIR)

    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        host_binding=f"{settings.HOST}:{settings.PORT}",
        platform=platform.platform(),
        uptime_seconds=round(time.time() - START_TIME, 2),
        database_connected=db_ok,
    )
