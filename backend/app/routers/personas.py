"""Persona metadata endpoint — powers the mobile persona quick-switcher
(TASK-039) via SDUI principles: labels/icons live server-side, so adding a
new persona never needs an app release.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.personas import ALL_PERSONAS, PERSONAS

router = APIRouter(prefix="/v1/personas", tags=["personas"])

# Material icon names the client maps to its local icon set.
_PERSONA_ICONS = {
    "health": "favorite_outline",
    "fitness": "directions_run_outlined",
    "coastal": "waves",
    "travel": "flight_takeoff_outlined",
    "family": "family_restroom_outlined",
    "farmer": "agriculture",
    "commuter": "train_outlined",
    "planner": "event_available_outlined",
}

_PERSONA_LABELS = {
    "health": "Health-conscious",
    "fitness": "Outdoor fitness",
    "coastal": "Beachgoer & surfer",
    "travel": "Traveler",
    "family": "Parent & family",
    "farmer": "Farmer & gardener",
    "commuter": "Daily commuter",
    "planner": "Event planner",
}

_PERSONA_TAGLINES = {
    "health": "AQI, UV and pollution-aware advisories",
    "fitness": "Best hours for outdoor workouts",
    "coastal": "Tides, swell and beach safety flags",
    "travel": "Multi-city forecasts and packing lists",
    "family": "School-commute storm warnings",
    "farmer": "Block-level crop advisories (GKMS)",
    "commuter": "Visibility, fog and rain delays",
    "planner": "10-day outdoor event suitability",
}


@router.get("")
async def list_personas() -> dict:
    return {
        "personas": [
            {
                "key": p,
                "label": _PERSONA_LABELS.get(p, p.title()),
                "icon": _PERSONA_ICONS.get(p, "person_outline"),
                "tagline": _PERSONA_TAGLINES.get(p, ""),
                "widgets": PERSONAS[p]["affinity"],
            }
            for p in ALL_PERSONAS
        ]
    }
