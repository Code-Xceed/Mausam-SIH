"""Mausam Next-Gen backend — FastAPI entrypoint.

Phase 0: health/ready probes, unified WeatherContext contract, SDUI and
telemetry skeletons, fixture-backed gateway with the API_MODE demo toggle.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.cache import cache
from app.core.config import settings
from app.core.logging import configure_logging
from app.routers import (
    admin,
    alerts,
    debug,
    favorites,
    geo,
    i18n,
    meta,
    personas,
    privacy,
    sdui,
    telemetry,
    weather,
)

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await cache.connect()
    logger.info(
        "%s v%s up | mode=%s | cache=%s",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.API_MODE,
        "redis" if cache.available else "none",
    )
    # Phase 6: CAP poller heartbeat (fixture feed in SEED, live URL if set).
    from app.services.cap_poller import poller

    poller.start()
    yield
    await poller.stop()
    await cache.close()


app = FastAPI(
    title="Mausam Next-Gen Gateway",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 9: restrict to app origins + admin portal
    allow_methods=["*"],
    allow_headers=["*"],
)
# TASK-059: gzip every JSON payload >500 B — geo tiles/SDUI ride far under
# the 60 KB-per-view budget on the wire.
app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(meta.router)
app.include_router(weather.router)
app.include_router(sdui.router)
app.include_router(telemetry.router)
app.include_router(favorites.router)
app.include_router(personas.router)
app.include_router(debug.router)
app.include_router(admin.router)
app.include_router(i18n.router)
app.include_router(alerts.router)
app.include_router(geo.router)
app.include_router(privacy.router)
