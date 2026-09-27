"""Public active-alerts endpoint — map-polygon feed (TASK-055 data half).

The mobile map renders CAP polygons with severity fills; this endpoint serves
the same store the gateway uses, with polygon coordinates as plain [lat, lon]
arrays for direct GeoJSON-style consumption. Coarse-only by design: polygon
vertices come from the official CAP feed (public safety information), and the
response carries no user identifiers whatsoever.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.alert_store import alert_store
from app.services.geofence import TargetSet

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

# Severity → mobile fill color (material red/orange/yellow scale).
SEVERITY_FILL = {
    "Extreme": "#B71C1C",
    "Severe": "#E65100",
    "Moderate": "#F9A825",
    "Minor": "#FDD835",
}


@router.get("/active")
async def active_alerts() -> dict[str, Any]:
    """All currently-active CAP alerts with map-ready polygons."""
    features: list[dict[str, Any]] = []
    for a in alert_store.active():
        targets = alert_store.targets_for(a.get("identifier", "")) or TargetSet()
        polys: list[list[list[float]]] = []
        for poly in a.get("polygons") or []:
            polys.append([[float(lat), float(lon)] for lat, lon in poly])
        features.append(
            {
                "identifier": a.get("identifier"),
                "event": a.get("event"),
                "severity": a.get("severity"),
                "headline": a.get("headline"),
                "area_desc": a.get("area_desc"),
                "expires": a.get("expires"),
                "injected": a.get("identifier") in alert_store._injected,
                "fill_color": SEVERITY_FILL.get(a.get("severity") or "", "#F9A825"),
                "area_wide": targets.area_wide,
                "coarse": targets.coarse,
                "polygons": polys,
            }
        )
    return {
        "type": "FeatureCollection",
        "count": len(features),
        "summary": alert_store.summary(),
        "features": features,
    }
