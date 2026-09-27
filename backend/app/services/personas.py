"""Persona definitions, affinity scoring, and urgency heuristics (Tier A).

The SDUI composer ranks widgets by:

    score(widget, persona, context) = 0.6 * persona_affinity
                                    + 0.4 * data_urgency

Phase 5 replaces this deterministic scoring with LinUCB bandit output; the
weights/shape stay identical so the swap is invisible to the client. Safety
widgets (disaster, commute) can pin to the top regardless of score — rules
veto rankings, ML only orders the rest (the architecture's core principle).
"""

from __future__ import annotations

from app.models.weather import WeatherCondition, WeatherContext

# --------------------------------------------------------------------------- #
# Personas
# --------------------------------------------------------------------------- #

PERSONAS: dict[str, dict[str, list[str]]] = {
    "health": {
        "affinity": ["aqi_radial_meter", "current_conditions", "visibility_meter"],
    },
    "fitness": {
        "affinity": ["running_window_timeline", "current_conditions"],
    },
    "coastal": {
        "affinity": ["marine_tide_gauge", "current_conditions", "travel_packing_carousel"],
    },
    "travel": {
        "affinity": ["travel_packing_carousel", "event_planner_calendar", "current_conditions"],
    },
    "family": {
        "affinity": ["commute_safety_banner", "current_conditions", "visibility_meter"],
    },
    "farmer": {
        "affinity": ["meghdoot_agro_card", "current_conditions"],
    },
    "commuter": {
        "affinity": ["commute_safety_banner", "visibility_meter", "current_conditions"],
    },
    "planner": {
        "affinity": ["event_planner_calendar", "current_conditions", "travel_packing_carousel"],
    },
}

ALL_PERSONAS = list(PERSONAS.keys())

# Explicitly requested personas (onboarding tags) get +50; others 0.
PERSONA_BOOST = 50.0

# Rank-bonus within one persona: 1st choice +30, 2nd +20, 3rd +10.
AFFINITY_RANK_BONUS = [30.0, 20.0, 10.0]

# --------------------------------------------------------------------------- #
# Widget <-> persona matrix (for the composer's default view)
# --------------------------------------------------------------------------- #

WIDGET_PERSONA_RELEVANCE: dict[str, list[str]] = {
    "aqi_radial_meter": ["health", "family"],
    "running_window_timeline": ["fitness"],
    "marine_tide_gauge": ["coastal"],
    "travel_packing_carousel": ["travel", "planner", "coastal"],
    "commute_safety_banner": ["commuter", "family"],
    "meghdoot_agro_card": ["farmer"],
    "visibility_meter": ["commuter", "family", "health"],
    "event_planner_calendar": ["planner", "travel"],
    "disaster_lifeline_card": [],  # everybody, when active — handled by pinning
    "current_conditions": [],      # universal baseline card
    "persona_rank_row": [],        # diagnostics row (Phase 5 inspector data)
}


def persona_affinity(widget_type: str, active_personas: list[str]) -> float:
    """0..100 affinity of a widget for the active persona set."""
    relevance = WIDGET_PERSONA_RELEVANCE.get(widget_type, [])
    if not relevance:
        return 40.0  # universal cards hover mid-scale
    overlap = set(relevance) & set(active_personas)
    if overlap:
        return 80.0 + 10.0 * min(len(overlap) - 1, 2)
    return 10.0


# --------------------------------------------------------------------------- #
# Data-driven urgency (0..100) — Tier A deterministic rules
# --------------------------------------------------------------------------- #


def _aqi_urgency(ctx: WeatherContext) -> float | None:
    if ctx.air_quality is None:
        return None
    a = ctx.air_quality.aqi
    if a >= 300:
        return 95.0
    if a >= 200:
        return 80.0
    if a >= 150:
        return 65.0
    if a >= 100:
        return 45.0
    return 25.0


def _marine_urgency(ctx: WeatherContext) -> float | None:
    m = ctx.marine
    if m is None:
        return None
    flag_score = {"red": 95.0, "yellow": 70.0, "green": 35.0}.get(m.beach_flag or "", 50.0)
    wave = m.significant_wave_height_m or 0.0
    wave_score = 90.0 if wave >= 2.5 else (70.0 if wave >= 1.5 else 40.0)
    return max(flag_score, wave_score)


def _commute_urgency(ctx: WeatherContext) -> float | None:
    """Thunderstorm/heavy-rain in hourly forecast overlapping commute windows."""
    windows = ((7, 9), (14, 16))
    bad_conditions = {WeatherCondition.THUNDERSTORM, WeatherCondition.RAIN}

    commute_hit = storm_hit = False
    for point in ctx.hourly:
        if point.condition not in bad_conditions:
            continue
        if any(start <= point.time.hour < end for start, end in windows):
            commute_hit = True
            if point.condition is WeatherCondition.THUNDERSTORM:
                storm_hit = True

    if storm_hit:
        return 95.0
    if commute_hit:
        return 85.0
    # Current conditions only (no hourly overlap): lesser urgency.
    if ctx.current.condition is WeatherCondition.THUNDERSTORM:
        return 75.0
    if ctx.current.condition is WeatherCondition.RAIN:
        return 60.0
    return None


def _visibility_urgency(ctx: WeatherContext) -> float | None:
    vis = ctx.current.visibility_m
    if vis is None:
        return None
    if vis < 200:
        return 95.0
    if vis < 500:
        return 80.0
    if vis < 1000:
        return 60.0
    if vis < 4000:
        return 35.0
    return 15.0


def _agro_urgency(ctx: WeatherContext) -> float | None:
    if ctx.agro is None:
        return None
    soil = ctx.agro.soil_moisture_pct
    if soil is not None and soil < 25:
        return 75.0
    return 45.0


def _travel_urgency(ctx: WeatherContext) -> float | None:
    rainy_days = sum(
        1 for d in ctx.daily if d.precipitation_probability_pct >= 50
    )
    if rainy_days >= 3:
        return 70.0
    if rainy_days >= 1:
        return 50.0
    return 20.0


def _event_urgency(ctx: WeatherContext) -> float | None:
    bad_days = sum(
        1
        for d in ctx.daily
        if d.precipitation_probability_pct >= 50
        or d.temp_max_c >= 38
        or d.temp_min_c <= 5
    )
    if bad_days >= 3:
        return 65.0
    if bad_days >= 1:
        return 45.0
    return 25.0


def _disaster_urgency(ctx: WeatherContext) -> float | None:
    if not ctx.cap_alerts:
        return None
    severities = {a.severity for a in ctx.cap_alerts}
    if "Extreme" in severities:
        return 100.0
    if "Severe" in severities:
        return 98.0
    return 70.0


URGENCY_RULES: dict[str, object] = {
    "aqi_radial_meter": _aqi_urgency,
    "marine_tide_gauge": _marine_urgency,
    "commute_safety_banner": _commute_urgency,
    "visibility_meter": _visibility_urgency,
    "meghdoot_agro_card": _agro_urgency,
    "travel_packing_carousel": _travel_urgency,
    "event_planner_calendar": _event_urgency,
    "disaster_lifeline_card": _disaster_urgency,
}
