"""Context vector pipeline (TASK-040): WeatherContext → LinUCB feature vector.

Feature layout (18 dims — superset of the DPR's 12-dim plan; extras documented
below. d stays configurable via BANDIT_CONTEXT_DIM for the pitch story).

    idx  feature                 source
    ───  ──────────────────────  ──────────────────────────────────────
     0   bias                    always 1.0 (intercept)
     1   sin(2πh/24)             hour of day, cyclic
     2   cos(2πh/24)             hour of day, cyclic
     3   temp_c / 50             current temperature, clipped [-1, 1]
     4   humidity / 100          current relative humidity
     5   wind / 50               current wind speed, clipped [0, ~2]
     6   aqi / 500               CPCB AQI, 0.0 when absent
     7   precip / 100            max 3-day rain probability
     8   has_marine              1.0 when INCOIS data present
     9   has_agro                1.0 when GKMS advisory present
    10   has_alert               1.0 when CAP alerts active
    11   fog_index               visibility-derived (MOSDAC proxy), 0 when clear
    12-19 persona one-hots        health fitness coastal travel family farmer
                                  commuter planner (onboarding tags, TASK-021)

All raw values are coarse or normalized — no PII, no raw GPS. Pure NumPy +
attribute reads: builds in well under 5 ms (benchmarked in tests).

Returns a dict per bandit convention: numeric vector for the dot products,
plus `feature_names` for the Algorithm Inspector's human-readable view.
"""

from __future__ import annotations

import math

import numpy as np

from app.models.weather import WeatherContext

FEATURE_NAMES: list[str] = [
    "bias",
    "hour_sin",
    "hour_cos",
    "temp_norm",
    "humidity",
    "wind_norm",
    "aqi_norm",
    "precip_norm",
    "has_marine",
    "has_agro",
    "has_alert",
    "fog_index",
    "persona:health",
    "persona:fitness",
    "persona:coastal",
    "persona:travel",
    "persona:family",
    "persona:farmer",
    "persona:commuter",
    "persona:planner",
]

PERSONA_KEYS = [
    "health", "fitness", "coastal", "travel",
    "family", "farmer", "commuter", "planner",
]

DIM = len(FEATURE_NAMES)  # 20

assert DIM == 12 + len(PERSONA_KEYS), "keep the DPR 12 + persona block layout"


def build_context_vector(
    ctx: WeatherContext,
    active_personas: list[str],
    *,
    reference_hour: float | None = None,
) -> dict:
    """x_t ∈ R^20 for the bandit. <5 ms; no I/O, no PII.

    `reference_hour` overrides wall-clock hour for deterministic tests.
    """
    now = ctx.generated_at
    hour = now.hour + now.minute / 60.0 if reference_hour is None else float(reference_hour)
    frac = 2.0 * math.pi * hour / 24.0

    aqi = ctx.air_quality.aqi if ctx.air_quality is not None else 0.0
    precip = max(
        (d.precipitation_probability_pct for d in ctx.daily[:3]), default=0
    )
    vis = ctx.current.visibility_m
    fog = 0.0 if vis is None else max(0.0, min(1.0, (4000 - vis) / 3800.0))

    persona_set = {p for p in active_personas if p in PERSONA_KEYS}

    x = np.array(
        [
            1.0,                                           # bias
            math.sin(frac),                                # hour cyclic
            math.cos(frac),
            max(-1.0, min(1.0, ctx.current.temperature_c / 50.0)),
            ctx.current.humidity_pct / 100.0,
            min(2.0, ctx.current.wind_kmph / 50.0),
            min(1.0, aqi / 500.0),
            precip / 100.0,
            1.0 if ctx.marine is not None else 0.0,
            1.0 if ctx.agro is not None else 0.0,
            1.0 if ctx.cap_alerts else 0.0,
            fog,
            *[1.0 if p in persona_set else 0.0 for p in PERSONA_KEYS],
        ],
        dtype=float,
    )

    return {"x": x, "feature_names": list(FEATURE_NAMES), "dim": DIM}
