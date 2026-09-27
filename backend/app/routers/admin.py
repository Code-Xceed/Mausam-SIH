"""Demo admin / Red-Alert injection tool (TASK-054).

The jury pitch needs a controlled disaster: one button injects a mock
Severe/Extreme CAP alert into the SAME pipeline live alerts travel
(poller → store → geofence → dispatcher), so the demo exercises the real
code path — no shortcuts, no fake UI state.

Endpoints (unauthenticated by design; Phase 9 adds an admin token):
    POST /v1/admin/inject-alert   — stage a Red alert (returns push bookkeeping)
    GET  /v1/admin/alerts         — active alerts + pipeline stats
    DELETE /v1/admin/alerts/injected — end the staged disaster
    POST /v1/admin/poll-now       — force one CAP poll cycle
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.alert_store import alert_store
from app.services.cities import CITIES, nearest_city
from app.services.geofence import circle_polygon

router = APIRouter(prefix="/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)


class InjectRequest(BaseModel):
    """Body for the staged-disaster injection. Everything optional."""

    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    city: str | None = Field(
        None, description="Demo city key (delhi/mumbai/kochi/vidarbha/shimla) — alt to lat/lon"
    )
    event: str = "Cyclone Warning"
    severity: str = Field("Extreme", pattern="^(Extreme|Severe|Moderate|Minor)$")
    headline: str | None = None
    description: str | None = None
    area_desc: str | None = None
    radius_deg: float = Field(0.35, gt=0, le=2.0, description="Polygon radius in lat degrees")
    validity_minutes: int = Field(120, ge=5, le=720)


@router.post("/inject-alert")
async def inject_alert(req: InjectRequest) -> dict[str, Any]:
    """Inject a mock Red alert and run the full dispatch pipeline on it."""
    t0 = time.perf_counter()

    lat, lon = req.lat, req.lon
    if lat is None or lon is None:
        city = next((c for c in CITIES if c.key == (req.city or "")), None)
        if city is None:
            city = nearest_city(lat or 28.6139, lon or 77.2090) if lat is not None else CITIES[0]
        lat, lon = city.lat, city.lon
        city_name = city.name
    else:
        city_name = nearest_city(lat, lon).name

    now = datetime.now(UTC)
    polygon = circle_polygon(lat, lon, radius_deg=req.radius_deg)
    alert: dict[str, Any] = {
        "identifier": f"demo-inject-{uuid.uuid4().hex[:12]}",
        "sender": "demo@mausam-nextgen.sih",
        "sent": now.isoformat(),
        "event": req.event,
        "severity": req.severity,
        "urgency": "Immediate",
        "certainty": "Observed",
        "headline": req.headline
        or f"{req.severity.upper()} {req.event} — {city_name} coastal belt (SIMULATED DRILL)",
        "description": req.description
        or f"Simulated {req.severity.lower()} {req.event.lower()} affecting {city_name} "
        "and surroundings. This is a DEMO DRILL injected for the Mausam Next-Gen "
        "emergency pipeline demonstration.",
        "area_desc": req.area_desc or f"{city_name} region (~{int(req.radius_deg * 111)} km radius)",
        "expires": (now + timedelta(minutes=req.validity_minutes)).isoformat(),
        "polygons": [polygon],
        "source": "NDMA_CAP",
        "injected": True,
    }

    alert_store.put(alert, injected=True)

    # Full pipeline: geofence + FCM dispatch (dry-run unless configured).
    from app.services.dispatcher import dispatch_alert

    bookkeeping = await dispatch_alert(alert)
    bookkeeping["inject_elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    bookkeeping["city"] = city_name
    bookkeeping["polygon_points"] = len(polygon)

    logger.info(
        "[admin] injected %s %s @ %s — %d topics in %.1fms",
        req.severity, req.event, city_name, bookkeeping["topics"],
        bookkeeping["inject_elapsed_ms"],
    )
    return {"alert": alert, "dispatch": bookkeeping}


@router.get("/alerts")
async def active_alerts() -> dict[str, Any]:
    """Everything the pipeline currently holds — the demo's control panel."""
    summary = alert_store.summary()
    alerts = []
    for a in alert_store.active():
        targets = alert_store.targets_for(a.get("identifier", ""))
        alerts.append(
            {
                "identifier": a.get("identifier"),
                "event": a.get("event"),
                "severity": a.get("severity"),
                "headline": a.get("headline"),
                "expires": a.get("expires"),
                "injected": a.get("identifier") in alert_store._injected,
                "target_cells": targets.size if targets else 0,
                "area_wide": targets.area_wide if targets else True,
            }
        )
    from app.services.cap_poller import poller
    from app.services.dispatcher import DRY_RUN

    return {
        "summary": summary,
        "alerts": alerts,
        "poller": {
            "running": poller._task is not None and not poller._task.done(),
            "interval_s": poller.interval_s,
            "poll_count": poller.poll_count,
            "last_poll_ts": poller.last_poll_ts,
            "last_error": poller.last_error,
        },
        "dispatcher_mode": "dry-run" if DRY_RUN else "live",
        "api_mode": settings.API_MODE,
    }


@router.delete("/alerts/injected")
async def clear_injected() -> dict[str, Any]:
    """End the staged disaster — removes demo-injected alerts only."""
    removed = alert_store.clear_injected()
    return {"removed": removed}


@router.post("/poll-now")
async def poll_now() -> dict[str, Any]:
    """Force one CAP poll cycle (bypasses the interval wait)."""
    from app.services.cap_poller import poller

    return await poller.poll_once()
