"""Liveness, readiness, and build info."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.cache import cache
from app.core.config import settings

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — must always return 200 when the process is up."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "api_mode": settings.API_MODE,
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
async def ready() -> dict:
    """Readiness probe — reports cache state without failing on its absence."""
    return {
        "status": "ok",
        "cache_backend": "redis" if cache.available else "none (in-process fallback)",
    }
